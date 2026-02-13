from rest_framework import serializers
from .models import CoachingReminder, Device, ReminderSchedule, NotificationLog


class CoachingReminderSerializer(serializers.ModelSerializer):
    """Serializer for CoachingReminder model"""
    
    class Meta:
        model = CoachingReminder
        fields = [
            'id', 'reminder_time', 'repeat_days', 'is_active', 
            'notification_enabled', 'timezone', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate_repeat_days(self, value):
        """Validate repeat_days field"""
        if not value:
            raise serializers.ValidationError("At least one day must be selected")
        
        valid_days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        for day in value:
            if day.lower() not in valid_days:
                raise serializers.ValidationError(f"Invalid day: {day}. Must be one of {valid_days}")
        
        return value
    
    def validate_timezone(self, value):
        """Validate timezone field"""
        import pytz
        try:
            pytz.timezone(value)
        except pytz.exceptions.UnknownTimeZoneError:
            raise serializers.ValidationError(f"Invalid timezone: {value}")
        
        return value


class DeviceSerializer(serializers.ModelSerializer):
    """Serializer for Device model"""
    
    class Meta:
        model = Device
        fields = [
            'id', 'device_id', 'device_type', 'device_name', 
            'app_version', 'os_version', 'is_active', 'last_seen', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'last_seen']
    
    def validate_device_type(self, value):
        """Validate device_type field"""
        valid_types = ['ios', 'android']
        if value not in valid_types:
            raise serializers.ValidationError(f"Invalid device type: {value}. Must be one of {valid_types}")
        
        return value


class ReminderScheduleSerializer(serializers.ModelSerializer):
    """Serializer for ReminderSchedule model"""
    
    class Meta:
        model = ReminderSchedule
        fields = [
            'id', 'scheduled_for', 'status', 'provider_message_id', 
            'attempts', 'last_attempt_at', 'error_message', 'created_at', 'sent_at'
        ]
        read_only_fields = ['id', 'created_at', 'sent_at']


class NotificationLogSerializer(serializers.ModelSerializer):
    """Serializer for NotificationLog model"""
    
    class Meta:
        model = NotificationLog
        fields = [
            'id', 'title', 'body', 'notification_type', 'provider_message_id',
            'delivery_status', 'delivered_at', 'opened_at', 'error_message', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'delivered_at', 'opened_at']


class CreateReminderSerializer(serializers.Serializer):
    """Serializer for creating reminders"""
    reminder_time = serializers.TimeField(required=True)
    repeat_days = serializers.ListField(
        child=serializers.CharField(),
        required=True,
        min_length=1
    )
    timezone = serializers.CharField(required=True)
    
    def validate_repeat_days(self, value):
        """Validate repeat_days field"""
        valid_days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        for day in value:
            if day.lower() not in valid_days:
                raise serializers.ValidationError(f"Invalid day: {day}. Must be one of {valid_days}")
        
        return value


class UpdateReminderSerializer(serializers.Serializer):
    """Serializer for updating reminders"""
    reminder_time = serializers.TimeField(required=False)
    repeat_days = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        min_length=1
    )
    is_active = serializers.BooleanField(required=False)
    timezone = serializers.CharField(required=False)
    
    def validate_repeat_days(self, value):
        """Validate repeat_days field"""
        if value:
            valid_days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            for day in value:
                if day.lower() not in valid_days:
                    raise serializers.ValidationError(f"Invalid day: {day}. Must be one of {valid_days}")
        
        return value


class NotificationToggleSerializer(serializers.Serializer):
    """Serializer for toggling notifications"""
    notification_enabled = serializers.BooleanField(required=True)
