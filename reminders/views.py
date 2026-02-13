from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from django.utils import timezone
from django.shortcuts import render
from datetime import datetime, timedelta
import pytz
from pytz import UTC

from .models import CoachingReminder, Device, ReminderSchedule, NotificationLog
from .serializers import (
    CoachingReminderSerializer, DeviceSerializer, ReminderScheduleSerializer,
    NotificationLogSerializer, CreateReminderSerializer, UpdateReminderSerializer,
    NotificationToggleSerializer
)
from reminders.services.onesignal_service import onesignal_service
from utils.response_format import (
    success_response, error_response, validation_error_response,
    created_response, not_found_response
)

class CoachingReminderViewSet(ModelViewSet):
    """ViewSet for managing coaching reminders"""
    serializer_class = CoachingReminderSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Return reminders for the authenticated user"""
        return CoachingReminder.objects.filter(user=self.request.user)
    
    def get_object(self):
        """Get or create reminder for the authenticated user"""
        # For other actions, use the default behavior
        return super().get_object()
    
    def list(self, request, *args, **kwargs):
        """Get user's coaching reminder (single reminder per user)"""
        try:
            reminder = CoachingReminder.objects.get(user=request.user)
            return success_response(
                message="Coaching reminder retrieved successfully",
                data=CoachingReminderSerializer(reminder).data
            )
        except CoachingReminder.DoesNotExist:
            return not_found_response(
                message="No coaching reminder found for user"
            )
    
    def create(self, request, *args, **kwargs):
        """Create a new coaching reminder"""
        serializer = CreateReminderSerializer(data=request.data)
        
        if not serializer.is_valid():
            return validation_error_response(
                message="Invalid reminder data",
                errors=serializer.errors
            )
        
        # Check if user already has a reminder
        if CoachingReminder.objects.filter(user=request.user).exists():
            return error_response(
                message="User already has a coaching reminder. Use PUT to update.",
                status_code=status.HTTP_400_BAD_REQUEST
            )
        
        # Use timezone from frontend
        timezone_str = serializer.validated_data['timezone']
        
        try:
            # Validate timezone
            pytz.timezone(timezone_str)
        except pytz.exceptions.UnknownTimeZoneError:
            return error_response(
                message="Invalid timezone",
                status_code=status.HTTP_400_BAD_REQUEST
            )
        
        # Create reminder
        reminder = CoachingReminder.objects.create(
            user=request.user,
            reminder_time=serializer.validated_data['reminder_time'],
            repeat_days=serializer.validated_data['repeat_days'],
            timezone=timezone_str,
            notification_enabled=False,  # Default to False, user must enable separately
            is_active=True
        )
        
        # Schedule reminders for the next 30 days
        schedule_reminders(reminder)
        
        return created_response(
            message="Coaching reminder created successfully",
            data=CoachingReminderSerializer(reminder).data
        )
    
    
    def destroy(self, request, *args, **kwargs):
        """Delete a coaching reminder"""
        # Get user's reminder (no ID required)
        try:
            instance = CoachingReminder.objects.get(user=request.user)
        except CoachingReminder.DoesNotExist:
            return not_found_response(
                message="No coaching reminder found for user"
            )
        
        # Cancel pending schedules
        ReminderSchedule.objects.filter(
            reminder=instance,
            status='pending'
        ).update(status='cancelled')
        
        instance.delete()
        
        return success_response(
            message="Coaching reminder deleted successfully"
        )
    
    @action(detail=False, methods=['put'], url_path='update')
    def update_reminder(self, request):
        """Update user's coaching reminder (PUT without ID)"""
        # Get or create reminder for the user (no ID required)
        instance, created = CoachingReminder.objects.get_or_create(
            user=request.user,
            defaults={
                'reminder_time': '09:00',
                'repeat_days': ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],
                'timezone': 'UTC',
                'is_active': True,
                'notification_enabled': False
            }
        )
        
        serializer = UpdateReminderSerializer(data=request.data)
        
        if not serializer.is_valid():
            return validation_error_response(
                message="Invalid reminder data",
                errors=serializer.errors
            )
        
        # Update fields
        if 'reminder_time' in serializer.validated_data:
            instance.reminder_time = serializer.validated_data['reminder_time']
        
        if 'repeat_days' in serializer.validated_data:
            instance.repeat_days = serializer.validated_data['repeat_days']
        
        if 'timezone' in serializer.validated_data:
            timezone_str = serializer.validated_data['timezone']
            try:
                pytz.timezone(timezone_str)
                instance.timezone = timezone_str
            except pytz.exceptions.UnknownTimeZoneError:
                return error_response(
                    message="Invalid timezone",
                    status_code=status.HTTP_400_BAD_REQUEST
                )
        
        if 'is_active' in serializer.validated_data:
            instance.is_active = serializer.validated_data['is_active']
        
        instance.save()
        
        # Reschedule reminders if time or days changed
        if any(field in serializer.validated_data for field in ['reminder_time', 'repeat_days', 'timezone']):
            # Cancel existing schedules
            ReminderSchedule.objects.filter(
                reminder=instance,
                status='pending'
            ).update(status='cancelled')
            
            # Schedule new reminders
            schedule_reminders(instance)
        
        return success_response(
            message="Coaching reminder updated successfully",
            data=CoachingReminderSerializer(instance).data
        )
    
    @action(detail=False, methods=['delete'], url_path='delete')
    def delete_reminder(self, request):
        """Delete user's coaching reminder (DELETE without ID)"""
        # Get user's reminder (no ID required)
        try:
            instance = CoachingReminder.objects.get(user=request.user)
        except CoachingReminder.DoesNotExist:
            return not_found_response(
                message="No coaching reminder found for user"
            )
        
        # Cancel pending schedules
        ReminderSchedule.objects.filter(
            reminder=instance,
            status='pending'
        ).update(status='cancelled')
        
        instance.delete()
        
        return success_response(
            message="Coaching reminder deleted successfully"
        )


class DeviceViewSet(ModelViewSet):
    """ViewSet for managing user devices"""
    serializer_class = DeviceSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Return devices for the authenticated user"""
        return Device.objects.filter(user=self.request.user)
    
    def create(self, request, *args, **kwargs):
        """Register a new device"""
        serializer = DeviceSerializer(data=request.data)
        
        if not serializer.is_valid():
            return validation_error_response(
                message="Invalid device data",
                errors=serializer.errors
            )
        
        # Check if device already exists
        device_id = serializer.validated_data['device_id']
        existing_device = Device.objects.filter(
            user=request.user,
            device_id=device_id
        ).first()
        
        if existing_device:
            # Update existing device
            for field, value in serializer.validated_data.items():
                setattr(existing_device, field, value)
            existing_device.is_active = True
            existing_device.last_seen = timezone.now()
            existing_device.save()
            
            return success_response(
                message="Device updated successfully",
                data=DeviceSerializer(existing_device).data
            )
        else:
            # Create new device
            device = serializer.save(
            user=request.user,
                is_active=True,
                last_seen=timezone.now()
        )
        
        return created_response(
            message="Device registered successfully",
                data=DeviceSerializer(device).data
        )


class NotificationLogViewSet(ModelViewSet):
    """ViewSet for viewing notification logs"""
    serializer_class = NotificationLogSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Return notification logs for the authenticated user"""
        return NotificationLog.objects.filter(user=self.request.user).order_by('-created_at')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_notifications(request):
    """Enable or disable notifications for user's reminder"""
    try:
        # Validate request data
        serializer = NotificationToggleSerializer(data=request.data)
        
        if not serializer.is_valid():
            return validation_error_response(
                message="Invalid notification toggle data",
                errors=serializer.errors
            )
        
        notification_enabled = serializer.validated_data['notification_enabled']
        
        # Check if reminder exists - don't create if it doesn't exist
        # try:
        #     reminder = CoachingReminder.objects.get(user=request.user)
        # except CoachingReminder.DoesNotExist:
        #     return error_response(
        #         message="Please create a reminder first",
        #         status_code=status.HTTP_404_NOT_FOUND
        #     )
        reminder, created = CoachingReminder.objects.get_or_create(
            user=request.user,
            defaults={
                "reminder_time": timezone.now().time(),                                 
                "notification_enabled": notification_enabled,
                "timezone": "UTC",                    
            }
        )
        # Toggle notification status
        reminder.notification_enabled = notification_enabled
        reminder.save()
        
        # If disabling notifications, cancel pending schedules
        if not notification_enabled:
            ReminderSchedule.objects.filter(
                reminder=reminder,
                status='pending'
            ).update(status='cancelled')
        
        action = "enabled" if notification_enabled else "disabled"
        return success_response(
            message=f"Notifications {action} successfully",
            data=CoachingReminderSerializer(reminder).data
        )
        
    except Exception as e:
        return error_response(
            message=f"Error toggling notifications: {str(e)}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def test_notification(request):
    """Send a test notification to user's devices"""
    try:
        # Get user's active devices
        devices = Device.objects.filter(
            user=request.user,
            is_active=True
        )
        
        if not devices.exists():
            return error_response(
                message="No active devices found",
                status_code=status.HTTP_404_NOT_FOUND
            )
        
        # Get device tokens
        device_tokens = [device.push_token for device in devices if device.push_token]
        
        if not device_tokens:
            return error_response(
                message="No valid device tokens found",
                status_code=status.HTTP_404_NOT_FOUND
            )
        
        # Send test notification
        title = "Test Notification"
        body = "This is a test notification from ZenCoach AI"
        
        response = onesignal_service.send_notification(
            player_ids=device_tokens,
            title=title,
            body=body,
            data={'type': 'test', 'timestamp': str(timezone.now())}
        )
        
        # Log the notification
        for device in devices:
            NotificationLog.objects.create(
                user=request.user,
                title=title,
                body=body,
                notification_type='test',
                delivery_status='sent' if response['success_count'] > 0 else 'failed',
                error_message=response.get('error')
            )
        
        if response['success_count'] > 0:
            return success_response(
                message=f"Test notification sent to {response['success_count']} device(s)",
                data=response
            )
        else:
            return error_response(
                message="Failed to send test notification",
                data=response,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        
    except Exception as e:
        return error_response(
            message="Error sending test notification",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


def schedule_reminders(reminder):
    """Schedule reminders for the next 30 days"""
    if not reminder.is_active or not reminder.notification_enabled:
        return
    
    # Get user's timezone
    user_tz = pytz.timezone(reminder.timezone)
    now = timezone.now().astimezone(user_tz)
    
    # Schedule for next 30 days
    for day_offset in range(30):
        target_date = now + timedelta(days=day_offset)
        target_weekday = target_date.strftime('%A').lower()
        
        # Check if this day is in repeat_days
        if target_weekday in reminder.repeat_days:
            # Create datetime for the reminder time
            reminder_datetime = user_tz.localize(
                datetime.combine(target_date.date(), reminder.reminder_time)
            )
            
            # Convert to UTC for storage
            reminder_datetime_utc = reminder_datetime.astimezone(UTC)
            
            # Only schedule if it's in the future
            if reminder_datetime_utc > timezone.now():
                ReminderSchedule.objects.get_or_create(
                    reminder=reminder,
                    scheduled_for=reminder_datetime_utc,
                    defaults={'status': 'pending'}
        )