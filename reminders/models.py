from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class CoachingReminder(models.Model):
    """User's coaching reminder settings"""
    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='coaching_reminder',
        help_text="User who owns this reminder"
    )
    
    # Time settings
    reminder_time = models.TimeField(
        help_text="Time of day for the reminder (e.g., 13:59 for 1:59 PM)"
    )
    
    # Repeat settings - store as JSON array of day names
    repeat_days = models.JSONField(
        default=list,
        help_text="Days of week to repeat: ['monday', 'tuesday', 'wednesday', 'sunday']"
    )
    
    # Notification settings
    is_active = models.BooleanField(
        default=True,
        help_text="Whether reminders are currently enabled"
    )
    
    notification_enabled = models.BooleanField(
        default=False,
        help_text="Whether user has granted notification permissions"
    )
    
    # Timezone for accurate scheduling
    timezone = models.CharField(
        max_length=50,
        default='UTC',
        help_text="User's timezone (e.g., 'America/New_York')"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'coaching_reminder'
        verbose_name = 'Coaching Reminder'
        verbose_name_plural = 'Coaching Reminders'
        indexes = [
            models.Index(fields=['is_active', 'notification_enabled']),
            models.Index(fields=['reminder_time']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.reminder_time} ({len(self.repeat_days)} days)"
    
    @property
    def is_configured(self):
        """Check if reminder is properly configured"""
        return (
            self.reminder_time and 
            len(self.repeat_days) > 0 and 
            self.notification_enabled and 
            self.is_active
        )


class Device(models.Model):
    """User's devices for push notifications"""
    
    DEVICE_TYPES = [
        ('ios', 'iOS'),
        ('android', 'Android'),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='devices',
        help_text="User who owns this device"
    )
    
    # Device identification
    device_id = models.CharField(
        max_length=255,
        help_text="Unique device identifier from mobile app"
    )
    
    device_type = models.CharField(
        max_length=10,
        choices=DEVICE_TYPES,
        help_text="Type of device"
    )
    
    # Push notification token (OneSignal player ID)
    push_token = models.CharField(
        max_length=500,
        help_text="OneSignal player ID for push notifications"
    )
    
    # Device metadata
    device_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Human-readable device name (e.g., 'John's iPhone')"
    )
    
    app_version = models.CharField(
        max_length=20,
        blank=True,
        help_text="App version installed on device"
    )
    
    os_version = models.CharField(
        max_length=20,
        blank=True,
        help_text="Operating system version"
    )
    
    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this device is currently active"
    )
    
    last_seen = models.DateTimeField(
        auto_now=True,
        help_text="Last time this device was seen"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'device'
        verbose_name = 'Device'
        verbose_name_plural = 'Devices'
        unique_together = ['user', 'device_id']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['device_type']),
            models.Index(fields=['last_seen']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.device_name or self.device_type}"


class ReminderSchedule(models.Model):
    """Individual scheduled reminder instances"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    reminder = models.ForeignKey(
        CoachingReminder,
        on_delete=models.CASCADE,
        related_name='schedules',
        help_text="Parent reminder this schedule belongs to"
    )
    
    # When to send this specific reminder
    scheduled_for = models.DateTimeField(
        help_text="Exact date and time to send this reminder"
    )
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        help_text="Current status of this scheduled reminder"
    )
    
    # Provider-specific message ID for tracking
    provider_message_id = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Firebase message ID or OneSignal notification ID"
    )
    
    # Retry logic
    attempts = models.PositiveIntegerField(
        default=0,
        help_text="Number of delivery attempts made"
    )
    
    last_attempt_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the last delivery attempt was made"
    )
    
    error_message = models.TextField(
        blank=True,
        help_text="Error message from last failed attempt"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the reminder was successfully sent"
    )
    
    class Meta:
        db_table = 'reminder_schedule'
        verbose_name = 'Reminder Schedule'
        verbose_name_plural = 'Reminder Schedules'
        ordering = ['scheduled_for']
        indexes = [
            models.Index(fields=['status', 'scheduled_for']),
            models.Index(fields=['reminder', 'scheduled_for']),
            models.Index(fields=['scheduled_for']),
        ]
    
    def __str__(self):
        return f"{self.reminder.user.email} - {self.scheduled_for} ({self.get_status_display()})"
    
    @property
    def is_overdue(self):
        """Check if this reminder is overdue"""
        return (
            self.status == 'pending' and 
            self.scheduled_for < timezone.now()
        )


class NotificationLog(models.Model):
    """Log of all notifications sent"""
    
    DELIVERY_STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
        ('opened', 'Opened'),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notification_logs',
        help_text="User who received the notification"
    )
    
    reminder = models.ForeignKey(
        CoachingReminder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notification_logs',
        help_text="Coaching reminder that triggered this notification"
    )
    
    schedule = models.ForeignKey(
        ReminderSchedule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notification_logs',
        help_text="Specific schedule instance that triggered this notification"
    )
    
    # Notification content
    title = models.CharField(
        max_length=200,
        help_text="Notification title"
    )
    
    body = models.TextField(
        help_text="Notification body/message"
    )
    
    notification_type = models.CharField(
        max_length=50,
        default='coaching_reminder',
        help_text="Type of notification (e.g., 'coaching_reminder', 'general')"
    )
    
    # Provider tracking
    provider_message_id = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Provider's message ID for tracking"
    )
    
    # Delivery tracking
    delivery_status = models.CharField(
        max_length=20,
        choices=DELIVERY_STATUS_CHOICES,
        default='sent',
        help_text="Current delivery status"
    )
    
    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the notification was delivered"
    )
    
    opened_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the user opened the notification"
    )
    
    # Error tracking
    error_message = models.TextField(
        blank=True,
        help_text="Error message if delivery failed"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'notification_log'
        verbose_name = 'Notification Log'
        verbose_name_plural = 'Notification Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['delivery_status']),
            models.Index(fields=['notification_type']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.title} ({self.get_delivery_status_display()})"
