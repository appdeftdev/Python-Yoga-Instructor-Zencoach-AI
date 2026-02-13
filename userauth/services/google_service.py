from google.auth.transport import requests
from google.oauth2 import id_token
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class GoogleAuthService:
    """Service for verifying Google OAuth tokens"""
    
    @staticmethod
    def verify_google_token(token):
        """
        Verify Google ID token and extract user information
        
        Args:
            token (str): Google ID token from frontend
            
        Returns:
            dict: User information if valid, None if invalid
        """
        try:
            # Verify the token
            idinfo = id_token.verify_oauth2_token(
                token, 
                requests.Request(), 
                settings.GOOGLE_CLIENT_ID
            )
            
            # Check if the token is from the correct issuer
            if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                logger.error(f"Invalid token issuer: {idinfo['iss']}")
                return None
            
            # Extract user information
            user_data = {
                'email': idinfo.get('email'),
                'first_name': idinfo.get('given_name', ''),
                'last_name': idinfo.get('family_name', ''),
                'profile_picture': idinfo.get('picture'),
                'google_id': idinfo.get('sub'),  # Google's unique user ID
                'registration_method': 'google',
                'is_verified': True  # Google verifies email
            }
            
            return user_data
            
        except ValueError as e:
            logger.error(f"Invalid Google token: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Google token verification error: {str(e)}")
            return None
