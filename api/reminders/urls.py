from django.urls import path, include
from rest_framework.routers import DefaultRouter
from reminders.views import (
    CoachingReminderViewSet, 
    DeviceViewSet, 
    NotificationLogViewSet,
    test_notification,
    toggle_notifications
)

# Create router for ViewSets
router = DefaultRouter()
router.register(r'coaching-reminder', CoachingReminderViewSet, basename='coaching-reminder')
router.register(r'devices', DeviceViewSet, basename='devices')
router.register(r'notification-logs', NotificationLogViewSet, basename='notification-logs')

urlpatterns = [
    # Include router URLs
    path('', include(router.urls)),
    
    # Additional API endpoints
    path('test-notification/', test_notification, name='test-notification'),
    path('toggle-notifications/', toggle_notifications, name='toggle-notifications'),
]
