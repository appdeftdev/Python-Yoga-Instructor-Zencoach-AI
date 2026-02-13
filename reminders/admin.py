# from django.contrib import admin
# from .models import CoachingReminder, Device, ReminderSchedule, NotificationLog


# @admin.register(CoachingReminder)
# class CoachingReminderAdmin(admin.ModelAdmin):
#     list_display = ['user', 'reminder_time', 'repeat_days', 'is_active', 'notification_enabled', 'created_at']
#     list_filter = ['is_active', 'notification_enabled', 'created_at']
#     search_fields = ['user__email', 'user__first_name', 'user__last_name']
#     readonly_fields = ['created_at', 'updated_at']


# @admin.register(Device)
# class DeviceAdmin(admin.ModelAdmin):
#     list_display = ['user', 'device_name', 'device_type', 'is_active', 'last_seen', 'created_at']
#     list_filter = ['device_type', 'is_active', 'created_at']
#     search_fields = ['user__email', 'device_name', 'device_id']
#     readonly_fields = ['created_at', 'last_seen']


# @admin.register(ReminderSchedule)
# class ReminderScheduleAdmin(admin.ModelAdmin):
#     list_display = ['reminder', 'scheduled_for', 'status', 'attempts', 'created_at']
#     list_filter = ['status', 'scheduled_for', 'created_at']
#     search_fields = ['reminder__user__email']
#     readonly_fields = ['created_at', 'sent_at']


# @admin.register(NotificationLog)
# class NotificationLogAdmin(admin.ModelAdmin):
#     list_display = ['user', 'title', 'delivery_status', 'created_at', 'delivered_at']
#     list_filter = ['delivery_status', 'notification_type', 'created_at']
#     search_fields = ['user__email', 'title', 'body']
#     readonly_fields = ['created_at', 'delivered_at', 'opened_at']