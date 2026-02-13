from rest_framework import serializers
from .models import (
    SubscriptionPlan, 
    UserSubscription, 
    PaymentMethod, 
    PaymentTransaction, 
    SubscriptionHistory
)
from userauth.serializers import UserProfileSerializer


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    """Serializer for subscription plans"""
    
    display_price = serializers.SerializerMethodField()
    trial_info = serializers.SerializerMethodField()
    monthly_price = serializers.SerializerMethodField()
    
    class Meta:
        model = SubscriptionPlan
        fields = [
            'id', 'name', 'description', 'price', 'original_price', 
            'billing_cycle', 'trial_days', 'features', 'is_popular', 
            'is_active', 'stripe_price_id', 'stripe_product_id',
            'display_price', 'trial_info', 'monthly_price',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_display_price(self, obj):
        return obj.get_display_price()
    
    def get_trial_info(self, obj):
        return obj.get_trial_info()
    
    def get_monthly_price(self, obj):
        if obj.billing_cycle == 'yearly':
            return round(float(obj.price) / 12, 2)
        return float(obj.price)


class UserSubscriptionSerializer(serializers.ModelSerializer):
    """Serializer for user subscriptions"""
    
    plan = SubscriptionPlanSerializer(read_only=True)
    plan_id = serializers.IntegerField(write_only=True)
    user = UserProfileSerializer(read_only=True)
    is_trial_active = serializers.SerializerMethodField()
    days_until_billing = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    next_billing_date = serializers.SerializerMethodField()
    
    class Meta:
        model = UserSubscription
        fields = [
            'id', 'user', 'plan', 'plan_id', 'status', 'stripe_subscription_id',
            'trial_start', 'trial_end', 'current_period_start', 'current_period_end',
            'cancel_at_period_end', 'cancelled_at', 'is_trial_active', 
            'days_until_billing', 'can_cancel', 'next_billing_date',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'stripe_subscription_id', 'trial_start', 'trial_end',
            'current_period_start', 'current_period_end', 'cancelled_at',
            'created_at', 'updated_at'
        ]
    
    def get_is_trial_active(self, obj):
        return obj.is_trial_active()
    
    def get_days_until_billing(self, obj):
        return obj.days_until_billing()
    
    def get_can_cancel(self, obj):
        return obj.can_cancel()
    
    def get_next_billing_date(self, obj):
        return obj.get_next_billing_date()


class PaymentMethodSerializer(serializers.ModelSerializer):
    """Serializer for payment methods"""
    
    display_name = serializers.SerializerMethodField()
    
    class Meta:
        model = PaymentMethod
        fields = [
            'id', 'type', 'is_default', 'stripe_payment_method_id',
            'card_last4', 'card_brand', 'card_exp_month', 'card_exp_year',
            'billing_address_line1', 'billing_address_line2', 'billing_city',
            'billing_state', 'billing_postal_code', 'billing_country',
            'display_name', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'stripe_payment_method_id', 'card_last4', 
            'card_brand', 'card_exp_month', 'card_exp_year', 'created_at', 'updated_at'
        ]
    
    def get_display_name(self, obj):
        return str(obj)


class PaymentTransactionSerializer(serializers.ModelSerializer):
    """Serializer for payment transactions"""
    
    user = UserProfileSerializer(read_only=True)
    subscription = UserSubscriptionSerializer(read_only=True)
    payment_method = PaymentMethodSerializer(read_only=True)
    is_successful = serializers.SerializerMethodField()
    payment_method_display = serializers.SerializerMethodField()
    can_refund = serializers.SerializerMethodField()
    
    class Meta:
        model = PaymentTransaction
        fields = [
            'id', 'user', 'subscription', 'payment_method', 'transaction_id',
            'amount', 'currency', 'status', 'payment_method_type',
            'stripe_payment_intent_id', 'stripe_charge_id', 'apple_pay_token',
            'google_pay_token', 'error_message', 'error_code', 'metadata',
            'is_successful', 'payment_method_display', 'can_refund',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'subscription', 'payment_method', 'transaction_id',
            'stripe_payment_intent_id', 'stripe_charge_id', 'apple_pay_token',
            'google_pay_token', 'error_message', 'error_code', 'created_at', 'updated_at'
        ]
    
    def get_is_successful(self, obj):
        return obj.is_successful()
    
    def get_payment_method_display(self, obj):
        return obj.get_payment_method_display()
    
    def get_can_refund(self, obj):
        return obj.can_refund()


class SubscriptionHistorySerializer(serializers.ModelSerializer):
    """Serializer for subscription history"""
    
    subscription = UserSubscriptionSerializer(read_only=True)
    
    class Meta:
        model = SubscriptionHistory
        fields = [
            'id', 'subscription', 'event_type', 'description', 
            'metadata', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


# Request/Response Serializers
class CreateSubscriptionSerializer(serializers.Serializer):
    """Serializer for creating new subscriptions"""
    
    plan_id = serializers.IntegerField()
    payment_method_id = serializers.IntegerField(required=False)
    payment_method_type = serializers.ChoiceField(
        choices=['stripe', 'apple_pay', 'google_pay'],
        required=False
    )
    apple_pay_token = serializers.CharField(required=False, allow_blank=True)
    google_pay_token = serializers.CharField(required=False, allow_blank=True)
    
    def validate(self, data):
        if not data.get('payment_method_id') and not data.get('apple_pay_token') and not data.get('google_pay_token'):
            raise serializers.ValidationError(
                "Either payment_method_id or payment token must be provided"
            )
        return data


class CancelSubscriptionSerializer(serializers.Serializer):
    """Serializer for cancelling subscriptions"""
    
    cancel_immediately = serializers.BooleanField(default=False)
    reason = serializers.CharField(required=False, allow_blank=True)


class CreatePaymentIntentSerializer(serializers.Serializer):
    """Serializer for creating payment intents"""
    
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField(max_length=3, default='USD')
    payment_method_id = serializers.IntegerField(required=False)
    payment_method_type = serializers.ChoiceField(
        choices=['stripe', 'apple_pay', 'google_pay']
    )
    apple_pay_token = serializers.CharField(required=False, allow_blank=True)
    google_pay_token = serializers.CharField(required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False, default=dict)


class CreatePaymentMethodSerializer(serializers.Serializer):
    """Serializer for saving payment methods (Card, Apple Pay, Google Pay)"""
    
    payment_type = serializers.ChoiceField(
        choices=['card', 'apple_pay', 'google_pay'],
        help_text="Only card, apple_pay, and google_pay are allowed"
    )
    
    # Card payment fields
    card = serializers.DictField(required=False)
    billing_address = serializers.DictField(required=False)
    
    # Apple Pay / Google Pay fields
    payment_token = serializers.CharField(
        required=False, 
        allow_blank=True,
        help_text="Stripe payment method ID (created by frontend from Apple Pay/Google Pay)"
    )
    
    def validate_payment_type(self, value):
        """Validate payment type is one of the 3 allowed types"""
        allowed_types = ['card', 'apple_pay', 'google_pay']
        if value not in allowed_types:
            raise serializers.ValidationError(
                f"Only {', '.join(allowed_types)} payment types are allowed"
            )
        return value
    
    def validate(self, data):
        payment_type = data.get('payment_type')
        
        if payment_type == 'card':
            if not data.get('card'):
                raise serializers.ValidationError("Card data is required for card payments")
        elif payment_type in ['apple_pay', 'google_pay']:
            if not data.get('payment_token'):
                raise serializers.ValidationError(f"Payment token is required for {payment_type} payments")
        
        return data


class WebhookSerializer(serializers.Serializer):
    """Serializer for webhook events"""
    
    event_type = serializers.CharField()
    data = serializers.JSONField()
    signature = serializers.CharField(required=False)
