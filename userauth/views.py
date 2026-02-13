from rest_framework import status, generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from django.contrib.auth import authenticate
from django.utils import timezone
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.http import JsonResponse
from .models import User, EmailVerification
from reminders.models import Device, CoachingReminder
from .serializers import (
    UserRegistrationSerializer, UserLoginSerializer, GoogleAuthSerializer,
    AppleAuthSerializer, TokenRefreshSerializer, UserProfileSerializer,
    SocialUserDataSerializer, UserProfileWithSubscriptionSerializer, EmailUpdateSerializer,
    PaymentMethodSerializer
)
from utils.response_format import (
    success_response, error_response, validation_error_response,
    unauthorized_response, created_response
)
from userauth.services.google_service import GoogleAuthService
from payments.models import UserSubscription
from payments.serializers import UserSubscriptionSerializer
from django.db import transaction, IntegrityError
from django.db.models import Q
import logging

from chat.models import Conversation

logger = logging.getLogger(__name__)
from reminders.models import CoachingReminder, Device, ReminderSchedule, NotificationLog
from payments.models import PaymentMethod, PaymentTransaction, UserSubscription, SubscriptionHistory

def register_device(user, device_id, push_token, device_type, device_name):
    """Register or update device for push notifications"""
    if not push_token or not device_id:
        return None
    
    device, created = Device.objects.update_or_create(
        user=user,
        device_id=device_id,
        defaults={
            'push_token': push_token,
            'device_type': device_type or 'ios',  # Default to iOS if not specified
            'device_name': device_name or f"{user.first_name}'s Device",
            'is_active': True,
            'last_seen': timezone.now()
        }
    )
    
    return device


def get_user_subscription_data(user):
    """
    Optimized helper function to fetch user subscription with related plan data.
    Uses select_related to avoid N+1 queries.
    """
    try:
        sub = UserSubscription.objects.select_related('plan').filter(
            user=user,
            status__in=['trial', 'active']
        ).first()
        if sub:
            return UserSubscriptionSerializer(sub).data
    except Exception:
        pass
    return None


@api_view(['POST'])
@permission_classes([AllowAny])
def register_view(request):
    """Optimized manual user registration endpoint"""
    serializer = UserRegistrationSerializer(data=request.data)
    
    if serializer.is_valid():
        try:
            # Use atomic transaction to ensure data consistency
            with transaction.atomic():
                user = serializer.save()
                # Generate JWT tokens
                refresh = RefreshToken.for_user(user)
                access_token = refresh.access_token
                
                # Prepare user data (optimized: only serialize needed fields)
                user_data = UserProfileSerializer(user).data
                
                # Get subscription with optimized query (select_related for plan)
                subscription = get_user_subscription_data(user)
                
                tokens = {
                    'access': str(access_token),
                    'refresh': str(refresh)
                }
                
                return created_response(
                    message="User registered successfully. Please login to continue.",
                    data={
                        'user': user_data,
                        'subscription': subscription,
                        'tokens': tokens,   
                    }
                )
        except IntegrityError as e:
            # Handle duplicate user error with proper JSON response
            error_message = str(e).lower()
            
            # Check for specific constraint violations
            if 'unique constraint' in error_message or 'duplicate key' in error_message:
                # Use the actual error message from the errors dict
                actual_error_msg = 'A user with this email address already exists. Please use a different email or try logging in.'
                
                if 'username' in error_message:
                    return validation_error_response(
                        message=actual_error_msg,
                        errors={
                            'email': [actual_error_msg]
                        }
                    )
                elif 'email' in error_message:
                    return validation_error_response(
                        message=actual_error_msg,
                        errors={
                            'email': [actual_error_msg]
                        }
                    )
                else:
                    # Generic unique constraint violation
                    return validation_error_response(
                        message=actual_error_msg,
                        errors={
                            'email': [actual_error_msg]
                        }
                    )
            else:
                # Generic integrity error - use the actual error message
                actual_error = str(e)
                return validation_error_response(
                    message=actual_error,
                    errors={'non_field_errors': [actual_error]}
                )
    
    # Extract the first error message from serializer errors for the main message
    error_message = "Registration failed"
    if serializer.errors:
        # Try to get the first error message from any field
        for field, errors in serializer.errors.items():
            if errors and isinstance(errors, list) and len(errors) > 0:
                error_message = errors[0] if isinstance(errors[0], str) else str(errors[0])
                break
            elif errors and isinstance(errors, str):
                error_message = errors
                break
    
    return validation_error_response(
        message=error_message,
        errors=serializer.errors
    )


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    """Optimized manual user login endpoint"""
    serializer = UserLoginSerializer(data=request.data)
    
    if serializer.is_valid():
        user = serializer.validated_data['user']
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        access_token = refresh.access_token
        
        # Prepare user data (optimized: only serialize needed fields)
        user_data = UserProfileSerializer(user).data
        
        # Get subscription with optimized query (select_related for plan)
        subscription = get_user_subscription_data(user)
        
        tokens = {
            'access': str(access_token),
            'refresh': str(refresh)
        }
        
        return success_response(
            message="Login successful",
            data={
                'user': user_data,
                'subscription': subscription,
                'tokens': tokens
            }
        )
    
    return validation_error_response(
        message="Login failed",
        errors=serializer.errors
    )


@api_view(['POST'])
@permission_classes([AllowAny])
def google_auth_view(request):
    """Optimized Google OAuth login/register endpoint"""
    try:
        serializer = GoogleAuthSerializer(data=request.data)
        
        if not serializer.is_valid():
            return validation_error_response(
                message="Invalid Google token",
                errors=serializer.errors
            )
        
        google_token = serializer.validated_data['google_token']
        
        # Check if GOOGLE_CLIENT_ID is configured
        if not getattr(settings, 'GOOGLE_CLIENT_ID', None):
            logger.error("GOOGLE_CLIENT_ID not configured")
            return error_response(
                message="Google authentication not configured",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        google_user_data = GoogleAuthService.verify_google_token(google_token)
        
        if not google_user_data:
            return error_response(
                message="Invalid Google token",
                status_code=status.HTTP_401_UNAUTHORIZED
            )
        
        email = google_user_data['email'].lower()
        google_id = google_user_data['google_id']
        
        # Optimized: Check if user exists by Google ID (indexed field)
        user = User.objects.filter(google_id=google_id).first()
        
        if user:
            # User exists, log them in
            # Register device if FCM token provided
            push_token = serializer.validated_data.get('push_token')
            device_id = serializer.validated_data.get('device_id')
            device_type = serializer.validated_data.get('device_type')
            device_name = serializer.validated_data.get('device_name')
            
            if push_token and device_id:
                register_device(user, device_id, push_token, device_type, device_name)
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            access_token = refresh.access_token
            
            # Prepare user data
            user_data = UserProfileSerializer(user).data
            
            # Get subscription with optimized query (select_related for plan)
            subscription = get_user_subscription_data(user)
            
            tokens = {
                'access': str(access_token),
                'refresh': str(refresh)
            }
            
            return success_response(
                message="Google login successful",
                data={
                    'user': user_data,
                    'subscription': subscription,
                    'tokens': tokens
                }
            )
        else:
            # Optimized: Check if user exists by email (use only() to avoid loading full object)
            if User.objects.filter(email=email).only('id').exists():
                # User exists but with different registration method
                return error_response(
                    message="Account already exists with different registration method",
                    status_code=status.HTTP_409_CONFLICT
                )
            else:
                # Create new user with atomic transaction
                try:
                    with transaction.atomic():
                        user = User.objects.create_user(
                            email=email,
                            username=email,
                            first_name=google_user_data['first_name'],
                            last_name=google_user_data['last_name'],
                            registration_method='google',
                            google_id=google_id,
                            profile_picture=google_user_data.get('profile_picture'),
                            is_verified=True  # Google verifies email
                        )
                        
                        # Register device for new users too
                        push_token = serializer.validated_data.get('push_token')
                        device_id = serializer.validated_data.get('device_id')
                        device_type = serializer.validated_data.get('device_type')
                        device_name = serializer.validated_data.get('device_name')
                        
                        if push_token and device_id:
                            register_device(user, device_id, push_token, device_type, device_name)
                        
                        # Generate JWT tokens
                        refresh = RefreshToken.for_user(user)
                        access_token = refresh.access_token
                        
                        # Prepare user data
                        user_data = UserProfileSerializer(user).data
                        
                        # New users won't have subscription
                        subscription = None
                        
                        tokens = {
                            'access': str(access_token),
                            'refresh': str(refresh)
                        }
                        
                        return created_response(
                            message="Google registration successful",
                            data={
                                'user': user_data,
                                'subscription': subscription,
                                'tokens': tokens
                            }
                        )
                except IntegrityError as e:
                    # Handle duplicate user error
                    error_message = str(e)
                    if 'username' in error_message.lower() or 'email' in error_message.lower():
                        return validation_error_response(
                            message="Registration failed",
                            errors={
                                'email': ['A user with this email already exists. Please try logging in.']
                            }
                        )
                    # Generic integrity error
                    return validation_error_response(
                        message="Registration failed",
                        errors={'non_field_errors': ['A user with this information already exists.']}
                    )
    
    except Exception as e:
        logger.error(f"Google authentication error: {str(e)}")
        return error_response(
            message="Google authentication failed",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def apple_auth_view(request):
    """Optimized Apple Sign In login/register endpoint"""
    serializer = AppleAuthSerializer(data=request.data)
    
    if not serializer.is_valid():
        return validation_error_response(
            message="Invalid Apple token",
            errors=serializer.errors
        )
    
    apple_token = serializer.validated_data['apple_token']
    
    try:
        # TODO: Implement actual Apple token verification
        # For now, we'll simulate the process
        # Note: Apple token verification requires additional setup
        apple_user_data = {
            'email': 'user@privaterelay.appleid.com',
            'first_name': 'John',
            'last_name': 'Doe',
            'profile_picture': None,
            'apple_id': 'apple_123456789',
            'registration_method': 'apple'
        }
        
        apple_id = apple_user_data['apple_id']
        email = apple_user_data.get('email', '').lower() if apple_user_data.get('email') else None
        
        # Optimized: Check if user exists by Apple ID (indexed field)
        user = User.objects.filter(apple_id=apple_id).first()
        
        if user:
            # User exists, log them in
            # Register device if FCM token provided
            push_token = serializer.validated_data.get('push_token')
            device_id = serializer.validated_data.get('device_id')
            device_type = serializer.validated_data.get('device_type')
            device_name = serializer.validated_data.get('device_name')
            
            if push_token and device_id:
                register_device(user, device_id, push_token, device_type, device_name)
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            access_token = refresh.access_token
            
            # Prepare user data
            user_data = UserProfileSerializer(user).data
            
            # Get subscription with optimized query (select_related for plan)
            subscription = get_user_subscription_data(user)
            
            tokens = {
                'access': str(access_token),
                'refresh': str(refresh)
            }
            
            return success_response(
                message="Apple login successful",
                data={
                    'user': user_data,
                    'subscription': subscription,
                    'tokens': tokens
                }
            )
        else:
            # Optimized: Check if user exists by email (use only() to avoid loading full object)
            if email and User.objects.filter(email=email).only('id').exists():
                # User exists but with different registration method
                return error_response(
                    message="Account already exists with different registration method",
                    status_code=status.HTTP_409_CONFLICT
                )
            else:
                # Create new user with atomic transaction
                try:
                    with transaction.atomic():
                        # Generate unique username if email not available
                        username = email if email else f"apple_user_{apple_id}"
                        
                        user = User.objects.create_user(
                            email=email,
                            username=username,
                            first_name=apple_user_data.get('first_name', ''),
                            last_name=apple_user_data.get('last_name', ''),
                            registration_method='apple',
                            apple_id=apple_id,
                            profile_picture=apple_user_data.get('profile_picture'),
                            is_verified=True  # Apple verifies email
                        )
                        
                        # Register device for new users too
                        push_token = serializer.validated_data.get('push_token')
                        device_id = serializer.validated_data.get('device_id')
                        device_type = serializer.validated_data.get('device_type')
                        device_name = serializer.validated_data.get('device_name')
                        
                        if push_token and device_id:
                            register_device(user, device_id, push_token, device_type, device_name)
                        
                        # Generate JWT tokens
                        refresh = RefreshToken.for_user(user)
                        access_token = refresh.access_token
                        
                        # Prepare user data
                        user_data = UserProfileSerializer(user).data
                        
                        # New users won't have subscription
                        subscription = None
                        
                        tokens = {
                            'access': str(access_token),
                            'refresh': str(refresh)
                        }
                        
                        return created_response(
                            message="Apple registration successful",
                            data={
                                'user': user_data,
                                'subscription': subscription,
                                'tokens': tokens
                            }
                        )
                except IntegrityError as e:
                    # Handle duplicate user error
                    error_message = str(e)
                    if 'username' in error_message.lower() or 'email' in error_message.lower():
                        return validation_error_response(
                            message="Registration failed",
                            errors={
                                'email': ['A user with this email already exists. Please try logging in.']
                            }
                        )
                    # Generic integrity error
                    return validation_error_response(
                        message="Registration failed",
                        errors={'non_field_errors': ['A user with this information already exists.']}
                    )
    
    except Exception as e:
        logger.error(f"Apple authentication error: {str(e)}")
        return error_response(
            message="Apple authentication failed",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def refresh_token_view(request):
    """JWT token refresh endpoint"""
    serializer = TokenRefreshSerializer(data=request.data)
    
    if not serializer.is_valid():
        return validation_error_response(
            message="Invalid refresh token",
            errors=serializer.errors
        )
    
    try:
        refresh_token = serializer.validated_data['refresh']
        refresh = RefreshToken(refresh_token)
        access_token = refresh.access_token
        
        return success_response(
            message="Token refreshed successfully",
            data={
                'access': str(access_token),
                'refresh': str(refresh)
            }
        )
    
    except TokenError:
        return unauthorized_response(
            message="Invalid or expired refresh token"
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def forgot_password_view(request):
    """Send password reset verification code to email"""
    try:
        email = request.data.get('email')
        
        if not email:
            return error_response(
                message="Email is required",
                status_code=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if user exists
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return error_response(
                message="No user found with this email address",
                status_code=status.HTTP_404_NOT_FOUND
            )
        
        # Generate verification code
        verification = EmailVerification.generate_code(email)
        
        # Debug email settings
        print(f"Email settings:")
        print(f"EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
        print(f"EMAIL_HOST: {settings.EMAIL_HOST}")
        print(f"EMAIL_PORT: {settings.EMAIL_PORT}")
        print(f"EMAIL_USE_SSL: {settings.EMAIL_USE_SSL}")
        print(f"EMAIL_HOST_USER: {settings.EMAIL_HOST_USER}")
        print(f"DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")
        
        # Send email
        subject = "Password Reset Verification Code"
        message = f"""
        Hi {user.first_name},
        
        You requested a password reset for your account.
        
        Your verification code is: {verification.verification_code}
        
        This code will expire in 15 minutes.
        
        Click the button below to reset your password:
        """
        
        # Create verification URL
        reset_url = f"{request.build_absolute_uri('/')}api/auth/reset-password/?code={verification.verification_code}&email={email}"
        
        html_message = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2>Password Reset Verification</h2>
            <p>Hi {user.first_name},</p>
            <p>You requested a password reset for your account.</p>
            <p><strong>Your verification code is: {verification.verification_code}</strong></p>
            <p>This code will expire in 15 minutes.</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{reset_url}" 
                   style="background-color: #007bff; color: white; padding: 12px 24px; 
                          text-decoration: none; border-radius: 5px; display: inline-block;">
                    Verify & Reset Password
                </a>
            </div>
            <p style="color: #666; font-size: 12px;">
                If the button doesn't work, copy and paste this link: {reset_url}
            </p>
        </body>
        </html>
        """
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False,
        )
        
        return success_response(
            message="Verification code sent to your email",
            data={"email": email}
        )
        
    except Exception as e:
        print(f"Email sending error: {str(e)}")  # Debug print
        return error_response(
            message=f"Failed to send verification code: {str(e)}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


def reset_password_view(request):
    """Show reset password form and process password reset"""
    if request.method == 'GET':
        # Show reset password form
        code = request.GET.get('code')
        email = request.GET.get('email')
        
        if not code or not email:
            return render(request, 'userauth/reset_password_error.html', {
                'error': 'Invalid reset link. Please request a new password reset.'
            })
        
        # Check if verification code is valid
        try:
            verification = EmailVerification.objects.get(
                email=email,
                verification_code=code
            )
        except EmailVerification.DoesNotExist:
            return render(request, 'userauth/reset_password_error.html', {
                'error': 'Invalid verification code. Please request a new password reset.'
            })
        
        # Check if code is expired
        if verification.is_expired:
            return render(request, 'userauth/reset_password_error.html', {
                'error': 'Verification code has expired. Please request a new password reset.'
            })
        
        # Check if code is already used
        if verification.is_used:
            return render(request, 'userauth/reset_password_error.html', {
                'error': 'Verification code has already been used. Please request a new password reset.'
            })
        
        # Show reset form
        return render(request, 'userauth/reset_password_form.html', {
            'code': code,
            'email': email
        })
    
    elif request.method == 'POST':
        # Process password reset
        code = request.POST.get('code')
        email = request.POST.get('email')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        # Validate inputs
        if not all([code, email, new_password, confirm_password]):
            return render(request, 'userauth/reset_password_form.html', {
                'code': code,
                'email': email,
                'error': 'All fields are required.'
            })
        
        if new_password != confirm_password:
            return render(request, 'userauth/reset_password_form.html', {
                'code': code,
                'email': email,
                'error': 'Passwords do not match.'
            })
        
        # Check verification code
        try:
            verification = EmailVerification.objects.get(
                email=email,
                verification_code=code
            )
        except EmailVerification.DoesNotExist:
            return render(request, 'userauth/reset_password_error.html', {
                'error': 'Invalid verification code.'
            })
        
        # Check if code is valid
        if not verification.is_valid:
            return render(request, 'userauth/reset_password_error.html', {
                'error': 'Verification code is invalid or expired.'
            })
        
        # Update user password
        try:
            user = User.objects.get(email=email)
            user.set_password(new_password)
            user.save()
            
            # Mark verification code as used
            verification.is_used = True
            verification.save()
            
            return render(request, 'userauth/reset_password_success.html', {
                'message': 'Password reset successfully! You can now login with your new password.'
            })
            
        except User.DoesNotExist:
            return render(request, 'userauth/reset_password_error.html', {
                'error': 'User not found.'
            })


class UserProfileView(generics.RetrieveAPIView):
    """
    GET /api/profile/
    Retrieve authenticated user's profile details along with subscription information
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        """Get user profile with subscription details"""
        try:
            user = request.user
            
            # Prepare user data
            user_data = UserProfileSerializer(user).data
            
            # Add subscription section
            subscription = None
            try:
                sub = UserSubscription.objects.filter(user=user).first()
                if sub and sub.status in ['trial', 'active']:
                    subscription = UserSubscriptionSerializer(sub).data
            except Exception:
                subscription = None
            
            # Add payment methods
            payment_methods = []
            try:
                methods = PaymentMethod.objects.filter(user=user, is_active=True).order_by('-is_default', '-created_at')
                payment_methods = PaymentMethodSerializer(methods, many=True).data
            except Exception:
                payment_methods = []
            
            # Add notification enabled status
            notification_enabled = False
            try:
                coaching_reminder = CoachingReminder.objects.filter(user=user).first()
                if coaching_reminder:
                    notification_enabled = coaching_reminder.notification_enabled
            except Exception:
                notification_enabled = False
            
            return success_response(
                message="User profile retrieved successfully",
                data={
                    'user': user_data,
                    'subscription': subscription or None,
                    'payment_methods': payment_methods,
                    'notification_enabled': notification_enabled
                }
            )
        except User.DoesNotExist:
            return error_response(
                message="User not found",
                status_code=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return error_response(
                message=f"An error occurred: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@api_view(['GET'])
@permission_classes([AllowAny])
def list_all_users(request):
    """
    API: Get all users list
    No authentication required, no parameters
    """
    try:
        users = User.objects.all().order_by('-created_at')
        user_data = UserProfileSerializer(users, many=True).data
        
        return success_response(
            message="Users retrieved successfully",
            data={
                'users': user_data,
                'total_count': len(user_data)
            }
        )
    except Exception as e:
        return error_response(
            message=f"Failed to retrieve users: {str(e)}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_email(request):
    """
    API to update user email
    Request body: {"email": "new@example.com"}
    """
    try:
        # Validate request data
        serializer = EmailUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_error_response(
                message="Invalid request data",
                errors=serializer.errors
            )
        
        new_email = serializer.validated_data['email']
        user = request.user
        
        # Update the user's email and username (since username is email)
        user.email = new_email
        user.username = new_email  # Update username to match new email
        user.save()
        
        return success_response(
            message="Email updated successfully",
            data={
                'email': user.email,
                'username': user.username
            }
        )
        
    except Exception as e:
        logger.error(f"Unexpected error in update_email API: {str(e)}")
        return error_response(
            message="An unexpected error occurred",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


def apple_test_view(request):
    """Serve the Apple Sign In test page"""
    return render(request, 'userauth/apple_test.html')


def apple_callback_view(request):
    """Handle Apple Sign In callback"""
    # Get URL parameters
    code = request.GET.get('code')
    id_token = request.GET.get('id_token')
    state = request.GET.get('state')
    error = request.GET.get('error')
    
    # Debug information
    debug_info = {
        'code': code,
        'id_token': id_token,
        'state': state,
        'error': error,
        'full_url': request.build_absolute_uri(),
        'query_params': dict(request.GET)
    }
    
    print("Apple Callback Debug:", debug_info)
    
    if error:
        return JsonResponse({
            'status': 'error',
            'message': f'Apple Sign In failed: {error}',
            'debug': debug_info
        })
    
    if id_token:
        # Process the Apple Sign In
        try:
            # For now, just return the token for testing
            return JsonResponse({
                'status': 'success',
                'message': 'Apple Sign In successful',
                'id_token': id_token,
                'authorization_code': code,
                'debug': debug_info
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f'Processing failed: {str(e)}',
                'debug': debug_info
            })
    
    return JsonResponse({
        'status': 'error',
        'message': 'No token received from Apple',
        'debug': debug_info
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def delete_user_data(request):
    """
    API: Delete all data associated with a user by email.
    Request body: {"email": "user@example.com"}
    """
    try:
        email = request.data.get('email')
        if not email:
            return validation_error_response(
                message="Email is required",
                errors={"email": ["This field is required."]}
            )
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return error_response(
                message="No user found with this email address",
                status_code=status.HTTP_404_NOT_FOUND
            )
        deleted_counts = {}
        with transaction.atomic():
            # Reminders-related
            count, _ = NotificationLog.objects.filter(user=user).delete()
            deleted_counts['notification_logs'] = count
            count, _ = Device.objects.filter(user=user).delete()
            deleted_counts['devices'] = count
            # CoachingReminder cascades ReminderSchedule
            count, _ = CoachingReminder.objects.filter(user=user).delete()
            deleted_counts['coaching_reminders'] = count
            
            # Chat-related (Messages cascade from Conversation)
            count, _ = Conversation.objects.filter(user=user).delete()
            deleted_counts['conversations'] = count
            
            # Payments-related
            count, _ = PaymentTransaction.objects.filter(user=user).delete()
            deleted_counts['payment_transactions'] = count
            # Delete histories by subscription or cascade after subscription delete
            subs = UserSubscription.objects.filter(user=user)
            hist_count = SubscriptionHistory.objects.filter(subscription__in=subs).count()
            SubscriptionHistory.objects.filter(subscription__in=subs).delete()
            deleted_counts['subscription_history'] = hist_count
            count, _ = PaymentMethod.objects.filter(user=user).delete()
            deleted_counts['payment_methods'] = count
            count, _ = subs.delete()
            deleted_counts['subscriptions'] = count
            
            # Email verifications
            count, _ = EmailVerification.objects.filter(email=user.email).delete()
            deleted_counts['email_verifications'] = count
            
            # Delete the user
            count, _ = user.delete()
            deleted_counts['user'] = count
        return success_response(
            message="User data deleted successfully",
            data={
                'email': email,
                'deleted': deleted_counts
            }
        )
    except Exception as e:
        return error_response(
            message=f"Failed to delete user data: {str(e)}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

