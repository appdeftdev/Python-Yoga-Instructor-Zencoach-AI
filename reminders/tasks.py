from celery import shared_task
from django.utils import timezone
from .models import ReminderSchedule, NotificationLog
from reminders.services.onesignal_service import onesignal_service
import logging

logger = logging.getLogger(__name__)


@shared_task
def send_reminder_task(reminder_schedule_id):
    """
    Celery task to send a reminder notification
    
    Args:
        reminder_schedule_id (int): ID of the ReminderSchedule record
    """
    try:
        # Get the reminder schedule
        schedule = ReminderSchedule.objects.get(id=reminder_schedule_id)
        
        # Check if already sent or cancelled
        if schedule.status in ['sent', 'cancelled']:
            logger.info(f"Reminder {reminder_schedule_id} already processed: {schedule.status}")
            return f"Reminder {reminder_schedule_id} already processed"
        
        # Update attempt count
        schedule.attempts += 1
        schedule.last_attempt_at = timezone.now()
        schedule.save()
        
        # Get user's active devices
        devices = schedule.reminder.user.devices.filter(is_active=True)
        
        if not devices.exists():
            schedule.status = 'failed'
            schedule.error_message = "No active devices found"
            schedule.save()
            logger.warning(f"No active devices for user {schedule.reminder.user.email}")
            return f"No active devices for reminder {reminder_schedule_id}"
        
        # Get valid push tokens (OneSignal Player IDs or FCM tokens)
        push_tokens = [device.push_token for device in devices if device.push_token and onesignal_service.validate_push_token(device.push_token)]
        
        if not push_tokens:
            schedule.status = 'failed'
            schedule.error_message = "No valid push tokens found"
            schedule.save()
            logger.warning(f"No valid push tokens for user {schedule.reminder.user.email}")
            return f"No valid push tokens for reminder {reminder_schedule_id}"
        
        # Prepare notification content
        title = "Coaching Reminder"
        body = "Time for your coaching session! Let's work on your goals."
        
        # Send notification
        response = onesignal_service.send_notification(
            player_ids=push_tokens,
            title=title,
            body=body,
            data={
                'type': 'coaching_reminder',
                'reminder_id': str(schedule.reminder.id),
                'schedule_id': str(schedule.id),
                'timestamp': str(timezone.now())
            }
        )
        
        # Update schedule status
        if response['success_count'] > 0:
            schedule.status = 'sent'
            schedule.sent_at = timezone.now()
            schedule.provider_message_id = response.get('message_ids', [None])[0]
            schedule.error_message = ""
            logger.info(f"Reminder {reminder_schedule_id} sent successfully to {response['success_count']} devices")
        else:
            schedule.status = 'failed'
            schedule.error_message = response.get('error', 'Unknown error')
            logger.error(f"Failed to send reminder {reminder_schedule_id}: {schedule.error_message}")
        
        schedule.save()
        
        # Log the notification
        for device in devices:
            NotificationLog.objects.create(
                user=schedule.reminder.user,
                reminder=schedule.reminder,
                schedule=schedule,
                title=title,
                body=body,
                notification_type='coaching_reminder',
                provider_message_id=schedule.provider_message_id,
                delivery_status='sent' if response['success_count'] > 0 else 'failed',
                error_message=schedule.error_message
            )
        
        return f"Reminder {reminder_schedule_id} processed: {schedule.status}"
        
    except ReminderSchedule.DoesNotExist:
        logger.error(f"ReminderSchedule {reminder_schedule_id} not found")
        return f"ReminderSchedule {reminder_schedule_id} not found"
        
    except Exception as e:
        logger.error(f"Error processing reminder {reminder_schedule_id}: {str(e)}")
        
        # Update schedule with error
        try:
            schedule = ReminderSchedule.objects.get(id=reminder_schedule_id)
            schedule.status = 'failed'
            schedule.error_message = str(e)
            schedule.save()
        except:
            pass
        
        return f"Error processing reminder {reminder_schedule_id}: {str(e)}"


@shared_task
def cleanup_old_schedules():
    """
    Cleanup old reminder schedules (older than 30 days)
    """
    try:
        from datetime import timedelta
        
        cutoff_date = timezone.now() - timedelta(days=30)
        
        # Delete old sent schedules
        old_schedules = ReminderSchedule.objects.filter(
            status='sent',
            sent_at__lt=cutoff_date
        )
        
        count = old_schedules.count()
        old_schedules.delete()
        
        logger.info(f"Cleaned up {count} old reminder schedules")
        return f"Cleaned up {count} old reminder schedules"
        
    except Exception as e:
        logger.error(f"Error cleaning up old schedules: {str(e)}")
        return f"Error cleaning up old schedules: {str(e)}"


@shared_task
def retry_failed_reminders():
    """
    Retry failed reminders (up to 3 attempts)
    """
    try:
        # Get failed reminders that haven't exceeded max attempts
        failed_schedules = ReminderSchedule.objects.filter(
            status='failed',
            attempts__lt=3,
            scheduled_for__gte=timezone.now() - timedelta(hours=1)  # Only retry recent failures
        )
        
        retry_count = 0
        for schedule in failed_schedules:
            # Reset status to pending for retry
            schedule.status = 'pending'
            schedule.error_message = ""
            schedule.save()
            
            # Schedule retry task
            send_reminder_task.apply_async(
                eta=timezone.now() + timedelta(minutes=5),  # Retry in 5 minutes
                args=[schedule.id]
            )
            
            retry_count += 1
        
        logger.info(f"Scheduled {retry_count} failed reminders for retry")
        return f"Scheduled {retry_count} failed reminders for retry"
        
    except Exception as e:
        logger.error(f"Error retrying failed reminders: {str(e)}")
        return f"Error retrying failed reminders: {str(e)}"
