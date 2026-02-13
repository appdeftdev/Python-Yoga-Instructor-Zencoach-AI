import requests
import json
from django.conf import settings
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class OneSignalService:
    """Service class for handling OneSignal push notifications"""
    
    def __init__(self):
        """Initialize OneSignal service with credentials"""
        self.app_id = settings.ONESIGNAL_APP_ID
        self.rest_api_key = settings.ONESIGNAL_REST_API_KEY
        self.url = "https://onesignal.com/api/v1/notifications"
        
        if not self.app_id or not self.rest_api_key:
            logger.error("OneSignal credentials not configured properly")
            raise ValueError("OneSignal credentials not configured")
    
    def send_notification(self, player_ids, title, body, data=None):
        """
        Send push notification to multiple devices using OneSignal
        
        Args:
            player_ids (list): List of OneSignal player IDs
            title (str): Notification title
            body (str): Notification body
            data (dict): Additional data payload
            
        Returns:
            dict: Response with success/failure counts
        """
        if not player_ids:
            return {
                'success_count': 0,
                'failure_count': 0,
                'responses': [],
                'error': 'No player IDs provided'
            }
        
        try:
            # Prepare the notification payload
            payload = {
                "app_id": self.app_id,
                "include_player_ids": player_ids,
                "headings": {"en": title},
                "contents": {"en": body},
                "data": data or {},
                "small_icon": "ic_notification",
                "large_icon": "ic_launcher",
                "android_accent_color": "FF000000",
                "priority": 10,
                "ttl": 3600,  # 1 hour TTL
                "collapse_id": f"coaching_reminder_{int(timezone.now().timestamp())}"
            }
            
            # Set headers
            headers = {
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Basic {self.rest_api_key}"
            }
            
            # Send the notification
            response = requests.post(
                self.url,
                headers=headers,
                data=json.dumps(payload)
            )
            
            response.raise_for_status()
            response_data = response.json()
            
            # Parse OneSignal response
            success_count = response_data.get('recipients', 0)
            failure_count = len(player_ids) - success_count
            
            logger.info(f"OneSignal notification sent: {success_count} success, {failure_count} failed")
            
            return {
                'success_count': success_count,
                'failure_count': failure_count,
                'responses': [{'success': True, 'message_id': response_data.get('id')}],
                'message_ids': [response_data.get('id')],
                'raw_response': response_data
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"OneSignal API request failed: {e}")
            return {
                'success_count': 0,
                'failure_count': len(player_ids),
                'responses': [],
                'error': f"OneSignal API error: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Failed to send OneSignal notification: {e}")
            return {
                'success_count': 0,
                'failure_count': len(player_ids),
                'responses': [],
                'error': str(e)
            }
    
    def send_single_notification(self, player_id, title, body, data=None):
        """
        Send push notification to a single device
        
        Args:
            player_id (str): OneSignal player ID
            title (str): Notification title
            body (str): Notification body
            data (dict): Additional data payload
            
        Returns:
            dict: Response with message_id or error
        """
        return self.send_notification([player_id], title, body, data)
    
    def validate_push_token(self, push_token):
        """
        Validate if push token is in correct format (OneSignal Player ID or FCM token)
        
        Args:
            push_token (str): Push token to validate
            
        Returns:
            bool: True if valid format, False otherwise
        """
        if not push_token:
            return False
        
        # Check if it's a OneSignal Player ID (UUID format)
        if len(push_token) == 36 and '-' in push_token:
            valid_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-')
            if all(c in valid_chars for c in push_token):
                return True
        
        # Check if it's an FCM token (longer string, no hyphens)
        if len(push_token) > 50 and '-' not in push_token:
            valid_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_')
            if all(c in valid_chars for c in push_token):
                return True
        
        return False
    
    def get_notification_status(self, notification_id):
        """
        Get the status of a sent notification
        
        Args:
            notification_id (str): OneSignal notification ID
            
        Returns:
            dict: Notification status information
        """
        try:
            url = f"https://onesignal.com/api/v1/notifications/{notification_id}"
            headers = {
                "Authorization": f"Basic {self.rest_api_key}"
            }
            
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Failed to get notification status: {e}")
            return {'error': str(e)}


# Global instance
onesignal_service = OneSignalService()
