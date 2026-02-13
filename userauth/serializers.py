from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from .models import User
from payments.models import UserSubscription, SubscriptionPlan, PaymentMethod


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for user registration"""
    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = [
            'email', 'password', 'password_confirm', 'first_name', 'last_name',
            'phone_number', 'date_of_birth'
        ]
        extra_kwargs = {
            'email': {'required': True},
            'first_name': {'required': True},
            'last_name': {'required': True},
        }
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Passwords don't match")
        return attrs
    
    def validate_email(self, value):
        """Validate that email and username (which equals email) don't already exist"""
        email_lower = value.lower()
        
        # Check if email already exists
        if User.objects.filter(email=email_lower).only('id').exists():
            raise serializers.ValidationError(
                "A user with this email address already exists. Please use a different email or try logging in."
            )
        
        # Check if username already exists (since username is set to email)
        if User.objects.filter(username=email_lower).only('id').exists():
            raise serializers.ValidationError(
                "A user with this email address already exists. Please use a different email or try logging in."
            )
        
        return value
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        email = validated_data.pop('email')
        
        user = User.objects.create_user(
            username=email.lower(),  # Use email as username
            email=email.lower(),
            registration_method='manual',
            **validated_data
        )
        user.set_password(password)
        user.save()
        return user


class UserLoginSerializer(serializers.Serializer):
    """Serializer for user login - WEB ONLY"""
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True)
    
    def validate(self, attrs):
        email = attrs.get('email').lower()
        password = attrs.get('password')
        
        if email and password:
            # authenticate() is already optimized by Django
            user = authenticate(username=email, password=password)
            if not user:
                raise serializers.ValidationError("Invalid email or password")
            if not user.is_active:
                raise serializers.ValidationError("User account is disabled")
            attrs['user'] = user
        else:
            raise serializers.ValidationError("Must include email and password")
        
        return attrs


class GoogleAuthSerializer(serializers.Serializer):
    """Serializer for Google OAuth authentication"""
    google_token = serializers.CharField(required=True)
    
    # Push notification fields (optional for web login)
    push_token = serializers.CharField(required=False, allow_blank=True)
    device_id = serializers.CharField(required=False, allow_blank=True)
    device_type = serializers.ChoiceField(
        choices=[('ios', 'iOS'), ('android', 'Android')],
        required=False
    )
    device_name = serializers.CharField(required=False, allow_blank=True)
    
    def validate_google_token(self, value):
        # TODO: Implement Google token validation
        # For now, we'll assume the token is valid
        # In production, you'd verify this with Google's API
        return value


class AppleAuthSerializer(serializers.Serializer):
    """Serializer for Apple Sign In authentication"""
    apple_token = serializers.CharField(required=True)
    
    # Push notification fields (optional for web login)
    push_token = serializers.CharField(required=False, allow_blank=True)
    device_id = serializers.CharField(required=False, allow_blank=True)
    device_type = serializers.ChoiceField(
        choices=[('ios', 'iOS'), ('android', 'Android')],
        required=False
    )
    device_name = serializers.CharField(required=False, allow_blank=True)
    
    def validate_apple_token(self, value):
        # TODO: Implement Apple token validation
        # For now, we'll assume the token is valid
        # In production, you'd verify this with Apple's API
        return value


class TokenRefreshSerializer(serializers.Serializer):
    """Serializer for JWT token refresh"""
    refresh = serializers.CharField(required=True)


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for user profile data"""
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'registration_method',
            'profile_picture', 'phone_number', 'date_of_birth', 'is_verified',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SocialUserDataSerializer(serializers.Serializer):
    """Serializer for social login user data"""
    email = serializers.EmailField(required=True)
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    profile_picture = serializers.URLField(required=False, allow_null=True)
    social_id = serializers.CharField(required=True)
    registration_method = serializers.ChoiceField(choices=User.REGISTRATION_METHODS)


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    """Serializer for subscription plan details"""
    
    class Meta:
        model = SubscriptionPlan
        fields = [
            'id', 'name', 'description', 'price', 'original_price', 
            'billing_cycle', 'trial_days', 'features', 'is_popular', 
            'is_active', 'get_display_price', 'get_trial_info'
        ]
        read_only_fields = ['get_display_price', 'get_trial_info']


class PaymentMethodSerializer(serializers.ModelSerializer):
    """Serializer for payment method details"""
    
    class Meta:
        model = PaymentMethod
        fields = [
            'id', 'type', 'is_default', 'is_active', 'expires_at',
            'card_last4', 'card_brand', 'card_exp_month', 'card_exp_year',
            'get_display_name', 'is_valid'
        ]
        read_only_fields = ['get_display_name', 'is_valid']


class UserSubscriptionSerializer(serializers.ModelSerializer):
    """Serializer for user subscription details"""
    plan = SubscriptionPlanSerializer(read_only=True)
    
    class Meta:
        model = UserSubscription
        fields = [
            'id', 'plan', 'status', 'stripe_subscription_id', 'stripe_customer_id',
            'trial_start', 'trial_end', 'current_period_start', 'current_period_end',
            'cancel_at_period_end', 'cancelled_at', 'promo_code_used', 
            'discount_applied', 'original_amount', 'is_trial_active',
            'days_until_billing', 'can_cancel', 'get_next_billing_date',
            'get_final_amount', 'has_promo_code'
        ]
        read_only_fields = [
            'is_trial_active', 'days_until_billing', 'can_cancel', 
            'get_next_billing_date', 'get_final_amount', 'has_promo_code'
        ]


class UserProfileWithSubscriptionSerializer(serializers.ModelSerializer):
    """Serializer for user profile with subscription details"""
    subscription = UserSubscriptionSerializer(read_only=True)
    payment_methods = PaymentMethodSerializer(many=True, read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'registration_method', 'google_id', 'apple_id', 'profile_picture',
            'phone_number', 'date_of_birth', 'is_verified', 'is_social_user',
            'social_id', 'created_at', 'updated_at', 'subscription', 'payment_methods'
        ]
        read_only_fields = [
            'id', 'is_social_user', 'social_id', 'created_at', 'updated_at'
        ]


class EmailUpdateSerializer(serializers.Serializer):
    """Serializer for email update request"""
    email = serializers.EmailField(
        required=True,
        help_text="New email address"
    )
    
    def validate_email(self, value):
        """Validate that the new email is not already in use"""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists")
        return value
