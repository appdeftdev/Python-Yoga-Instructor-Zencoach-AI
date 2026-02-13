import stripe
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

# Configure Stripe
stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', None)

class StripeService:
    """Service for handling Stripe API operations"""
    
    def __init__(self):
        if not stripe.api_key:
            logger.warning("Stripe API key not configured")
    
    def create_customer(self, user):
        """Create a Stripe customer for the user"""
        try:
            customer = stripe.Customer.create(
                email=user.email,
                name=f"{user.first_name} {user.last_name}".strip(),
                metadata={
                    'user_id': user.id,
                    'created_at': timezone.now().isoformat()
                }
            )
            return {
                'success': True,
                'data': {'customer_id': customer.id}
            }
        except stripe.error.StripeError as e:
            logger.error(f"Stripe customer creation failed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def create_payment_method(self, card_data):
        """Create a Stripe payment method from card data or test token"""
        try:
            # Check if it's a test token (starts with 'tok_')
            if card_data['number'].startswith('tok_'):
                # For test tokens, create a real Stripe payment method
                payment_method = stripe.PaymentMethod.create(
                    type='card',
                    card={
                        'token': card_data['number']  # Use the test token directly
                    }
                )
                return {
                    'success': True,
                    'data': {'payment_method': payment_method}
                }
            else:
                # For raw card data (if enabled)
                payment_method = stripe.PaymentMethod.create(
                    type='card',
                    card={
                        'number': card_data['number'],
                        'exp_month': card_data['exp_month'],
                        'exp_year': card_data['exp_year'],
                        'cvc': card_data['cvc']
                    }
                )
                return {
                    'success': True,
                    'data': {'payment_method': payment_method}
                }
        except stripe.error.StripeError as e:
            logger.error(f"Stripe payment method creation failed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def create_google_pay_payment_method(self, google_pay_token):
        """Create a Stripe payment method from Google Pay token"""
        try:
            # Google Pay tokens are already Stripe payment method IDs
            # Just retrieve the existing payment method
            payment_method = stripe.PaymentMethod.retrieve(google_pay_token)
            return {
                'success': True,
                'data': {'payment_method': payment_method}
            }
        except stripe.error.StripeError as e:
            logger.error(f"Stripe Google Pay payment method retrieval failed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def create_apple_pay_payment_method(self, apple_pay_token):
        """Create a Stripe payment method from Apple Pay token"""
        try:
            # Apple Pay tokens are already Stripe payment method IDs
            # Just retrieve the existing payment method
            payment_method = stripe.PaymentMethod.retrieve(apple_pay_token)
            return {
                'success': True,
                'data': {'payment_method': payment_method}
            }
        except stripe.error.StripeError as e:
            logger.error(f"Stripe Apple Pay payment method retrieval failed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def attach_payment_method(self, payment_method_id, customer_id):
        """Attach payment method to customer"""
        try:
            stripe.PaymentMethod.attach(
                payment_method_id,
                customer=customer_id
            )
            return {
                'success': True,
                'data': {'attached': True}
            }
        except stripe.error.StripeError as e:
            logger.error(f"Stripe payment method attachment failed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def detach_payment_method(self, payment_method_id):
        """Detach payment method from customer"""
        try:
            stripe.PaymentMethod.detach(payment_method_id)
            return {
                'success': True,
                'data': {'detached': True}
            }
        except stripe.error.StripeError as e:
            logger.error(f"Stripe payment method detachment failed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_payment_method(self, payment_method_id):
        """Get payment method details from Stripe"""
        try:
            payment_method = stripe.PaymentMethod.retrieve(payment_method_id)
            return {
                'success': True,
                'data': {'payment_method': payment_method}
            }
        except stripe.error.StripeError as e:
            logger.error(f"Stripe payment method retrieval failed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def list_customer_payment_methods(self, customer_id, type='card'):
        """List all payment methods for a customer"""
        try:
            payment_methods = stripe.PaymentMethod.list(
                customer=customer_id,
                type=type
            )
            return {
                'success': True,
                'data': {'payment_methods': payment_methods.data}
            }
        except stripe.error.StripeError as e:
            logger.error(f"Stripe payment methods listing failed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def create_payment_intent(self, amount, currency, customer_id, payment_method_id=None):
        """Create a payment intent for subscription payment"""
        try:
            intent_data = {
                'amount': int(amount * 100),  # Convert to cents
                'currency': currency,
                'customer': customer_id,
                'metadata': {
                    'created_at': timezone.now().isoformat()
                }
            }
            
            if payment_method_id:
                intent_data['payment_method'] = payment_method_id
                intent_data['confirmation_method'] = 'manual'
                intent_data['confirm'] = True
            
            payment_intent = stripe.PaymentIntent.create(**intent_data)
            
            return {
                'success': True,
                'data': {'payment_intent': payment_intent}
            }
        except stripe.error.StripeError as e:
            logger.error(f"Stripe payment intent creation failed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def create_subscription(self, customer_id, price_id, payment_method_id=None, trial_period_days=None):
        """Create a Stripe subscription"""
        try:
            subscription_data = {
                'customer': customer_id,
                'items': [{'price': price_id}],
                'payment_behavior': 'default_incomplete',
                'payment_settings': {'save_default_payment_method': 'on_subscription'},
                'expand': ['latest_invoice.payment_intent']
            }
            
            # Add payment method if provided
            if payment_method_id:
                subscription_data['default_payment_method'] = payment_method_id
                subscription_data['payment_behavior'] = 'default_incomplete'
            
            if trial_period_days and trial_period_days > 0:
                subscription_data['trial_period_days'] = trial_period_days
            else:
                # For non-trial subscriptions, ensure immediate payment
                subscription_data['payment_behavior'] = 'default_incomplete'
            
            subscription = stripe.Subscription.create(**subscription_data)
            
            return {
                'success': True,
                'data': {'subscription': subscription}
            }
        except stripe.error.StripeError as e:
            logger.error(f"Stripe subscription creation failed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
