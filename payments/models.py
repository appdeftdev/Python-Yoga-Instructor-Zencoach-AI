from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal

User = get_user_model()

class PromoCode(models.Model):
    """Promo codes for discounts"""
    
    DISCOUNT_TYPE_CHOICES = [
        ('percentage', 'Percentage'),
        ('fixed', 'Fixed Amount'),
    ]
    
    code = models.CharField(
        max_length=50, 
        unique=True,
        help_text="Promo code (e.g., WELCOME20)"
    )
    discount_type = models.CharField(
        max_length=20,
        choices=DISCOUNT_TYPE_CHOICES,
        help_text="Type of discount"
    )
    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Discount amount or percentage"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this promo code is active"
    )
    valid_from = models.DateTimeField(
        help_text="Start date for promo code validity"
    )
    valid_until = models.DateTimeField(
        help_text="End date for promo code validity"
    )
    usage_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum number of times this code can be used (null = unlimited)"
    )
    used_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of times this code has been used"
    )
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Description of the promo code"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'promo_codes'
        ordering = ['-created_at']
        verbose_name = "Promo Code"
        verbose_name_plural = "Promo Codes"
    
    def __str__(self):
        return f"{self.code} - {self.discount_value}{'%' if self.discount_type == 'percentage' else '$'}"
    
    def is_valid(self):
        """Check if promo code is valid"""
        now = timezone.now()
        return (
            self.is_active and
            self.valid_from <= now <= self.valid_until and
            (self.usage_limit is None or self.used_count < self.usage_limit)
        )
    
    def can_be_used_by_user(self, user):
        """Check if user can use this promo code"""
        if not self.is_valid():
            return False
        
        # Check if user already used this code
        return not UserSubscription.objects.filter(
            user=user,
            promo_code_used=self.code
        ).exists()


class SubscriptionPlan(models.Model):
    """Defines available subscription plans"""
    
    BILLING_CYCLE_CHOICES = [
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    original_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Original price before discount"
    )
    billing_cycle = models.CharField(
        max_length=20, 
        choices=BILLING_CYCLE_CHOICES
    )
    trial_days = models.PositiveIntegerField(
        default=0,
        help_text="Number of free trial days"
    )
    features = models.JSONField(
        default=list,
        help_text="List of features included in this plan"
    )
    is_popular = models.BooleanField(
        default=False,
        help_text="Mark as most popular plan"
    )
    is_active = models.BooleanField(default=True)
    
    # Stripe integration
    stripe_price_id = models.CharField(
        max_length=100, 
        unique=True, 
        null=True, 
        blank=True,
        help_text="Stripe Price ID for this plan"
    )
    stripe_product_id = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        help_text="Stripe Product ID for this plan"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'subscription_plans'
        ordering = ['price']
        verbose_name = "Subscription Plan"
        verbose_name_plural = "Subscription Plans"
    
    def __str__(self):
        return f"{self.name} - ${self.price}/{self.billing_cycle}"
    
    def get_display_price(self):
        """Format price for display"""
        return f"${self.price:.2f}"
    
    def get_trial_info(self):
        """Get trial period information"""
        if self.trial_days > 0:
            return f"{self.trial_days} days free trial"
        return "No trial period"
    
    def is_popular_plan(self):
        """Check if this is the popular plan"""
        return self.is_popular


class UserSubscription(models.Model):
    """Tracks user's current subscription"""
    
    STATUS_CHOICES = [
        ('trial', 'Trial'),
        ('active', 'Active'),
        ('past_due', 'Past Due'),
        ('cancelled', 'Cancelled'),
        ('unpaid', 'Unpaid'),
    ]
    
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE,
        related_name='subscription'
    )
    plan = models.ForeignKey(
        SubscriptionPlan, 
        on_delete=models.CASCADE,
        related_name='subscriptions'
    )
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES,
        default='trial'
    )
    
    # Stripe integration
    stripe_subscription_id = models.CharField(
        max_length=100, 
        unique=True, 
        null=True, 
        blank=True,
        help_text="Stripe Subscription ID"
    )
    stripe_customer_id = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        help_text="Stripe Customer ID"
    )
    
    # Trial period
    trial_start = models.DateTimeField(null=True, blank=True)
    trial_end = models.DateTimeField(null=True, blank=True)
    
    # Billing period
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()
    
    # Cancellation
    cancel_at_period_end = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    
    # Promo code
    promo_code_used = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Promo code used for this subscription"
    )
    discount_applied = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Discount amount applied"
    )
    original_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Original amount before discount"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_subscriptions'
        verbose_name = "User Subscription"
        verbose_name_plural = "User Subscriptions"
    
    def __str__(self):
        return f"{self.user.email} - {self.plan.name} ({self.status})"
    
    def is_trial_active(self):
        """Check if currently in trial period"""
        if not self.trial_end:
            return False
        return timezone.now() < self.trial_end and self.status == 'trial'
    
    def days_until_billing(self):
        """Calculate days until next billing"""
        if self.status in ['cancelled', 'unpaid']:
            return None
        delta = self.current_period_end - timezone.now()
        return max(0, delta.days)
    
    def can_cancel(self):
        """Check if subscription can be cancelled"""
        return self.status in ['active', 'trial'] and not self.cancel_at_period_end
    
    def get_next_billing_date(self):
        """Get next billing date"""
        if self.status in ['cancelled', 'unpaid']:
            return None
        return self.current_period_end
    
    def get_final_amount(self):
        """Get final amount after discount"""
        if self.original_amount:
            return self.original_amount - self.discount_applied
        return self.plan.price - self.discount_applied
    
    def has_promo_code(self):
        """Check if subscription used a promo code"""
        return bool(self.promo_code_used)


class PaymentMethod(models.Model):
    """User's saved payment methods - Only 3 types allowed"""
    
    PAYMENT_TYPE_CHOICES = [
        ('card', 'Credit/Debit Card'),
        ('apple_pay', 'Apple Pay'),
        ('google_pay', 'Google Pay'),
    ]
    
    CARD_BRAND_CHOICES = [
        ('visa', 'Visa'),
        ('mastercard', 'Mastercard'),
        ('amex', 'American Express'),
        ('discover', 'Discover'),
        ('diners', 'Diners Club'),
        ('jcb', 'JCB'),
        ('unionpay', 'UnionPay'),
        ('unknown', 'Unknown'),
    ]
    
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE,
        related_name='payment_methods'
    )
    type = models.CharField(
        max_length=20, 
        choices=PAYMENT_TYPE_CHOICES
    )
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, help_text="Whether this payment method is active")
    expires_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Expiration date for payment tokens (Apple Pay, Google Pay)"
    )
    
    # Stripe integration (only for card payments)
    stripe_payment_method_id = models.CharField(
        max_length=100, 
        unique=True,
        null=True,
        blank=True,
        help_text="Stripe Payment Method ID (only for card payments)"
    )
    
    # Card details (encrypted)
    card_last4 = models.CharField(max_length=4, null=True, blank=True)
    card_brand = models.CharField(
        max_length=20, 
        choices=CARD_BRAND_CHOICES,
        null=True, 
        blank=True
    )
    card_exp_month = models.PositiveIntegerField(null=True, blank=True)
    card_exp_year = models.PositiveIntegerField(null=True, blank=True)
    
    # Apple Pay / Google Pay
    apple_pay_token = models.TextField(null=True, blank=True)
    google_pay_token = models.TextField(null=True, blank=True)
    
    # Billing Address
    billing_address_line1 = models.CharField(
        max_length=255, 
        null=True, 
        blank=True,
        help_text="Billing address line 1"
    )
    billing_address_line2 = models.CharField(
        max_length=255, 
        null=True, 
        blank=True,
        help_text="Billing address line 2 (apartment, suite, etc.)"
    )
    billing_city = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        help_text="Billing city"
    )
    billing_state = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        help_text="Billing state/province"
    )
    billing_postal_code = models.CharField(
        max_length=20, 
        null=True, 
        blank=True,
        help_text="Billing postal/ZIP code"
    )
    billing_country = models.CharField(
        max_length=2, 
        null=True, 
        blank=True,
        help_text="Billing country (ISO 3166-1 alpha-2 code)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'payment_methods'
        ordering = ['-is_default', '-created_at']
        verbose_name = "Payment Method"
        verbose_name_plural = "Payment Methods"
        constraints = [
            models.CheckConstraint(
                check=models.Q(type__in=['card', 'apple_pay', 'google_pay']),
                name='only_3_payment_types_allowed'
            )
        ]
    
    def __str__(self):
        if self.type == 'card' and self.card_last4:
            return f"{self.get_card_brand_display()} ****{self.card_last4}"
        elif self.type == 'apple_pay':
            return f"Apple Pay (Token: {self.apple_pay_token[:10]}...)" if self.apple_pay_token else "Apple Pay"
        elif self.type == 'google_pay':
            return f"Google Pay (Token: {self.google_pay_token[:10]}...)" if self.google_pay_token else "Google Pay"
        return f"{self.get_type_display()}"
    
    def save(self, *args, **kwargs):
        # Ensure only one default payment method per user
        if self.is_default:
            PaymentMethod.objects.filter(
                user=self.user, 
                is_default=True
            ).update(is_default=False)
        super().save(*args, **kwargs)
    
    def is_valid(self):
        """Check if payment method is valid and not expired"""
        if not self.is_active:
            return False
        
        # Check if token is expired (for Apple Pay, Google Pay)
        if self.expires_at and self.expires_at < timezone.now():
            return False
        
        return True
    
    def get_display_name(self):
        """Get user-friendly display name"""
        if self.type == 'card' and self.card_last4:
            return f"{self.get_card_brand_display()} ****{self.card_last4}"
        elif self.type == 'apple_pay':
            return "Apple Pay"
        elif self.type == 'google_pay':
            return "Google Pay"
        return self.get_type_display()


class PaymentTransaction(models.Model):
    """Records all payment attempts and transactions"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('succeeded', 'Succeeded'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('stripe', 'Stripe'),
        ('apple_pay', 'Apple Pay'),
        ('google_pay', 'Google Pay'),
    ]
    
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE,
        related_name='payment_transactions'
    )
    subscription = models.ForeignKey(
        UserSubscription, 
        on_delete=models.CASCADE,
        related_name='transactions',
        null=True, 
        blank=True
    )
    payment_method = models.ForeignKey(
        PaymentMethod, 
        on_delete=models.SET_NULL,
        related_name='transactions',
        null=True, 
        blank=True
    )
    
    # Transaction details
    transaction_id = models.CharField(
        max_length=100, 
        unique=True,
        help_text="Internal transaction ID"
    )
    amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    currency = models.CharField(
        max_length=3, 
        default='USD'
    )
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    # Payment method used
    payment_method_type = models.CharField(
        max_length=20, 
        choices=PAYMENT_METHOD_CHOICES
    )
    
    # External payment IDs
    stripe_payment_intent_id = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        help_text="Stripe Payment Intent ID"
    )
    stripe_charge_id = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        help_text="Stripe Charge ID"
    )
    apple_pay_token = models.TextField(null=True, blank=True)
    google_pay_token = models.TextField(null=True, blank=True)
    
    # Error handling
    error_message = models.TextField(null=True, blank=True)
    error_code = models.CharField(max_length=50, null=True, blank=True)
    
    # Promo code
    promo_code_used = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Promo code used for this transaction"
    )
    discount_applied = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Discount amount applied"
    )
    original_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Original amount before discount"
    )
    
    # Metadata
    metadata = models.JSONField(
        default=dict,
        help_text="Additional transaction metadata"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'payment_transactions'
        ordering = ['-created_at']
        verbose_name = "Payment Transaction"
        verbose_name_plural = "Payment Transactions"
    
    def __str__(self):
        return f"{self.user.email} - ${self.amount} ({self.status})"
    
    def is_successful(self):
        """Check if payment succeeded"""
        return self.status == 'succeeded'
    
    def get_payment_method_display(self):
        """Human-readable payment method"""
        return self.get_payment_method_type_display()
    
    def can_refund(self):
        """Check if payment can be refunded"""
        return (
            self.status == 'succeeded' and 
            self.created_at > timezone.now() - timezone.timedelta(days=120)
        )
    
    def get_final_amount(self):
        """Get final amount after discount"""
        if self.original_amount:
            return self.original_amount - self.discount_applied
        return self.amount
    
    def has_promo_code(self):
        """Check if transaction used a promo code"""
        return bool(self.promo_code_used)


class SubscriptionHistory(models.Model):
    """Tracks subscription changes and events"""
    
    EVENT_TYPE_CHOICES = [
        ('created', 'Created'),
        ('trial_started', 'Trial Started'),
        ('trial_ended', 'Trial Ended'),
        ('activated', 'Activated'),
        ('renewed', 'Renewed'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
        ('payment_failed', 'Payment Failed'),
        ('payment_succeeded', 'Payment Succeeded'),
    ]
    
    subscription = models.ForeignKey(
        UserSubscription, 
        on_delete=models.CASCADE,
        related_name='history'
    )
    event_type = models.CharField(
        max_length=20, 
        choices=EVENT_TYPE_CHOICES
    )
    description = models.TextField()
    metadata = models.JSONField(
        default=dict,
        help_text="Additional event metadata"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Subscription History"
        verbose_name_plural = "Subscription Histories"
    
    def __str__(self):
        return f"{self.subscription.user.email} - {self.get_event_type_display()}"
