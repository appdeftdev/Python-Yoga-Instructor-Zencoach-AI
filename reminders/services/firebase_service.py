import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class FirebaseService:
    """Service class for handling Firebase Cloud Messaging"""
    
    def __init__(self):
        """Initialize Firebase Admin SDK"""
        if not firebase_admin._apps:
            try:
                cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
                firebase_admin.initialize_app(cred)
                logger.info("Firebase Admin SDK initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Firebase: {e}")
                raise
    
    def send_notification(self, device_tokens, title, body, data=None):
        """
        Send push notification to multiple devices
        
        Args:
            device_tokens (list): List of FCM tokens
            title (str): Notification title
            body (str): Notification body
            data (dict): Additional data payload
            
        Returns:
            dict: Response with success/failure counts
        """
        if not device_tokens:
            return {
                'success_count': 0,
                'failure_count': 0,
                'responses': [],
                'error': 'No device tokens provided'
            }
        
        try:
            # For older Firebase versions, send individual messages
            success_count = 0
            failure_count = 0
            responses = []
            message_ids = []
            
            for token in device_tokens:
                try:
                    # Create single message
                    message = messaging.Message(
                        notification=messaging.Notification(
                            title=title,
                            body=body
                        ),
                        data=data or {},
                        token=token
                    )
                    
                    # Send notification
                    response = messaging.send(message)
                    success_count += 1
                    responses.append({'success': True, 'message_id': response})
                    message_ids.append(response)
                    logger.info(f"Notification sent to token {token[:10]}...: {response}")
                    
                except Exception as e:
                    failure_count += 1
                    responses.append({'success': False, 'error': str(e)})
                    logger.error(f"Failed to send to token {token[:10]}...: {e}")
            
            logger.info(f"Notification batch completed: {success_count} success, {failure_count} failed")
            
            return {
                'success_count': success_count,
                'failure_count': failure_count,
                'responses': responses,
                'message_ids': message_ids
            }
            
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return {
                'success_count': 0,
                'failure_count': len(device_tokens),
                'responses': [],
                'error': str(e)
            }
    
    def send_single_notification(self, device_token, title, body, data=None):
        """
        Send push notification to a single device
        
        Args:
            device_token (str): FCM token
            title (str): Notification title
            body (str): Notification body
            data (dict): Additional data payload
            
        Returns:
            dict: Response with message_id or error
        """
        try:
            # Create single message
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body
                ),
                data=data or {},
                token=device_token
            )
            
            # Send notification
            response = messaging.send(message)
            
            logger.info(f"Single notification sent successfully: {response}")
            
            return {
                'success': True,
                'message_id': response,
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Failed to send single notification: {e}")
            return {
                'success': False,
                'message_id': None,
                'error': str(e)
            }
    
    def validate_token(self, device_token):
        """
        Validate if FCM token is in correct format
        
        Args:
            device_token (str): FCM token to validate
            
        Returns:
            bool: True if valid format, False otherwise
        """
        if not device_token:
            return False
        
        # Basic validation - FCM tokens are usually long strings
        if len(device_token) < 50:
            return False
        
        # Check if it contains valid characters
        valid_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_')
        if not all(c in valid_chars for c in device_token):
            return False
        
        return True


# Global instance
firebase_service = FirebaseService()
