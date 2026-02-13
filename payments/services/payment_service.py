from django.contrib.auth import get_user_model
from django.utils import timezone
from ..models import PaymentMethod, UserSubscription, PaymentTransaction
from .stripe_service import StripeService
from utils.response_format import success_response, error_response
import stripe
import uuid
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

class PaymentService:
    """Service for handling payment operations"""
    
    def __init__(self):
        self.stripe_service = StripeService()
    
    def save_payment_method(self, user, payment_type, data):
        """Save any payment method type with business rules"""
        try:
            # Validate payment type
            allowed_types = ['card', 'apple_pay', 'google_pay']
            if payment_type not in allowed_types:
                return error_response(
                    f"Invalid payment type. Only {', '.join(allowed_types)} are allowed"
                )
            
            # Allow multiple payment methods per type and no hard cap
            
            # Check if this is the first payment method (set as default)
            is_first_method = not PaymentMethod.objects.filter(user=user).exists()
            
            # Save payment method based on type
            if payment_type == 'card':
                return self._save_card_payment_method(user, data, is_first_method)
            elif payment_type == 'apple_pay':
                return self._save_apple_pay_payment_method(user, data, is_first_method)
            elif payment_type == 'google_pay':
                return self._save_google_pay_payment_method(user, data, is_first_method)
            
        except Exception as e:
            logger.error(f"Payment method save failed: {str(e)}")
            return error_response(f"Failed to save payment method: {str(e)}")
    
    def _save_card_payment_method(self, user, data, is_first_method):
        """Save card payment method"""
        try:
            card_data = data['card']
            billing_address = data.get('billing_address')
            
            # Create Stripe customer if doesn't exist
            if not hasattr(user, 'subscription') or not user.subscription.stripe_customer_id:
                customer_result = self.stripe_service.create_customer(user)
                if not customer_result['success']:
                    return error_response(f"Failed to create customer: {customer_result['error']}")
                
                customer_id = customer_result['data']['customer_id']
            else:
                customer_id = user.subscription.stripe_customer_id
            
            # Create Stripe payment method
            payment_method_result = self.stripe_service.create_payment_method(card_data)
            if not payment_method_result['success']:
                return error_response(f"Failed to create payment method: {payment_method_result['error']}")
            
            stripe_payment_method = payment_method_result['data']['payment_method']
            
            # Attach to customer
            attach_result = self.stripe_service.attach_payment_method(
                stripe_payment_method['id'], 
                customer_id
            )
            if not attach_result['success']:
                return error_response(f"Failed to attach payment method: {attach_result['error']}")
            
            # Save to local database
            payment_method_data = {
                'user': user,
                'type': 'card',
                'stripe_payment_method_id': stripe_payment_method['id'],
                'card_last4': stripe_payment_method['card']['last4'],
                'card_brand': stripe_payment_method['card']['brand'],
                'card_exp_month': stripe_payment_method['card']['exp_month'],
                'card_exp_year': stripe_payment_method['card']['exp_year'],
                'is_default': is_first_method
            }
            
            # Add billing address if provided
            if billing_address:
                payment_method_data.update({
                    'billing_address_line1': billing_address.get('line1'),
                    'billing_address_line2': billing_address.get('line2'),
                    'billing_city': billing_address.get('city'),
                    'billing_state': billing_address.get('state'),
                    'billing_postal_code': billing_address.get('postal_code'),
                    'billing_country': billing_address.get('country')
                })
            
            payment_method = PaymentMethod.objects.create(**payment_method_data)
            
            # Update user subscription with customer ID if needed
            if hasattr(user, 'subscription') and not user.subscription.stripe_customer_id:
                user.subscription.stripe_customer_id = customer_id
                user.subscription.save()
            
            return success_response(
                "Card payment method saved successfully",
                data={'payment_method_id': payment_method.id, 'is_default': is_first_method}
            )
            
        except Exception as e:
            logger.error(f"Card payment method save failed: {str(e)}")
            return error_response(f"Failed to save card payment method: {str(e)}")
    
    def _save_apple_pay_payment_method(self, user, data, is_first_method):
        """Save Apple Pay payment method using Stripe"""
        try:
            payment_token = data['payment_token']  # This is actually a Stripe payment method ID
            
            # Create Stripe customer if doesn't exist
            if not hasattr(user, 'subscription') or not user.subscription.stripe_customer_id:
                customer_result = self.stripe_service.create_customer(user)
                if not customer_result['success']:
                    return error_response(f"Failed to create customer: {customer_result['error']}")
                
                customer_id = customer_result['data']['customer_id']
            else:
                customer_id = user.subscription.stripe_customer_id
            
            # Retrieve the Stripe payment method (it's already created by frontend)
            payment_method_result = self.stripe_service.create_apple_pay_payment_method(payment_token)
            if not payment_method_result['success']:
                return error_response(f"Failed to retrieve Apple Pay payment method: {payment_method_result['error']}")
            
            stripe_payment_method = payment_method_result['data']['payment_method']
            
            # Attach to customer
            attach_result = self.stripe_service.attach_payment_method(
                stripe_payment_method['id'], 
                customer_id
            )
            if not attach_result['success']:
                return error_response(f"Failed to attach payment method: {attach_result['error']}")
            
            # Save to local database
            payment_method = PaymentMethod.objects.create(
                user=user,
                type='apple_pay',
                stripe_payment_method_id=stripe_payment_method['id'],
                apple_pay_token=stripe_payment_method['id'],  # Store Stripe ID for reference
                is_default=is_first_method
            )
            
            # Update user subscription with customer ID if needed
            if hasattr(user, 'subscription') and not user.subscription.stripe_customer_id:
                user.subscription.stripe_customer_id = customer_id
                user.subscription.save()
            
            return success_response(
                "Apple Pay payment method saved successfully",
                data={'payment_method_id': payment_method.id, 'is_default': is_first_method}
            )
            
        except Exception as e:
            logger.error(f"Apple Pay payment method save failed: {str(e)}")
            return error_response(f"Failed to save Apple Pay payment method: {str(e)}")
    
    def _save_google_pay_payment_method(self, user, data, is_first_method):
        """Save Google Pay payment method using Stripe"""
        try:
            payment_token = data['payment_token']  # This is actually a Stripe payment method ID
            
            # Create Stripe customer if doesn't exist
            if not hasattr(user, 'subscription') or not user.subscription.stripe_customer_id:
                customer_result = self.stripe_service.create_customer(user)
                if not customer_result['success']:
                    return error_response(f"Failed to create customer: {customer_result['error']}")
                
                customer_id = customer_result['data']['customer_id']
            else:
                customer_id = user.subscription.stripe_customer_id
            
            # Retrieve the Stripe payment method (it's already created by frontend)
            payment_method_result = self.stripe_service.create_google_pay_payment_method(payment_token)
            if not payment_method_result['success']:
                return error_response(f"Failed to retrieve Google Pay payment method: {payment_method_result['error']}")
            
            stripe_payment_method = payment_method_result['data']['payment_method']
            
            # Attach to customer
            attach_result = self.stripe_service.attach_payment_method(
                stripe_payment_method['id'], 
                customer_id
            )
            if not attach_result['success']:
                return error_response(f"Failed to attach payment method: {attach_result['error']}")
            
            # Save to local database
            payment_method = PaymentMethod.objects.create(
                user=user,
                type='google_pay',
                stripe_payment_method_id=stripe_payment_method['id'],
                google_pay_token=stripe_payment_method['id'],  # Store Stripe ID for reference
                is_default=is_first_method
            )
            
            # Update user subscription with customer ID if needed
            if hasattr(user, 'subscription') and not user.subscription.stripe_customer_id:
                user.subscription.stripe_customer_id = customer_id
                user.subscription.save()
            
            return success_response(
                "Google Pay payment method saved successfully",
                data={'payment_method_id': payment_method.id, 'is_default': is_first_method}
            )
            
        except Exception as e:
            logger.error(f"Google Pay payment method save failed: {str(e)}")
            return error_response(f"Failed to save Google Pay payment method: {str(e)}")
    
    def get_saved_payment_methods(self, user):
        """Get all saved payment methods for the user"""
        try:
            payment_methods = PaymentMethod.objects.filter(user=user, is_active=True).order_by('-is_default', '-created_at')

            # Serialize payment methods
            from ..serializers import PaymentMethodSerializer
            serializer = PaymentMethodSerializer(payment_methods, many=True)
            
            return success_response(
                "Payment methods retrieved successfully",
                data={
                    'payment_methods': serializer.data,
                    'total_count': len(payment_methods)
                }
            )
            
        except Exception as e:
            logger.error(f"Payment methods retrieval failed: {str(e)}")
            return error_response(f"Failed to get payment methods: {str(e)}")
    
    def get_payment_methods(self, user):
        """Get all payment methods for the user (legacy method)"""
        return self.get_saved_payment_methods(user)
    
    def set_default_payment_method(self, user, payment_method_id):
        """Set a payment method as default"""
        try:
            # Get the payment method
            try:
                payment_method = PaymentMethod.objects.get(
                    id=payment_method_id, 
                    user=user
                )
            except PaymentMethod.DoesNotExist:
                return error_response("Payment method not found", status_code=404)
            
            # Unset all other default methods
            PaymentMethod.objects.filter(
                user=user, 
                is_default=True
            ).update(is_default=False)
            
            # Set this one as default
            payment_method.is_default = True
            payment_method.save()
            
            from ..serializers import PaymentMethodSerializer
            serializer = PaymentMethodSerializer(payment_method)
            
            return success_response(
                "Default payment method updated successfully",
                data={'payment_method': serializer.data}
            )
            
        except Exception as e:
            logger.error(f"Default payment method update failed: {str(e)}")
            return error_response(f"Failed to update default payment method: {str(e)}")
    
    def delete_payment_method(self, user, payment_method_id):
        """Delete a payment method"""
        try:
            # Get the payment method
            try:
                payment_method = PaymentMethod.objects.get(
                    id=payment_method_id, 
                    user=user
                )
            except PaymentMethod.DoesNotExist:
                return error_response("Payment method not found", status_code=404)
            
            # Detach from Stripe
            detach_result = self.stripe_service.detach_payment_method(
                payment_method.stripe_payment_method_id
            )
            if not detach_result['success']:
                logger.warning(f"Failed to detach from Stripe: {detach_result['error']}")
            
            # Delete from local database
            payment_method.delete()
            
            return success_response("Payment method deleted successfully")
            
        except Exception as e:
            logger.error(f"Payment method deletion failed: {str(e)}")
            return error_response(f"Failed to delete payment method: {str(e)}")
    
    def create_payment_intent(self, user, amount, currency='USD', payment_method_id=None):
        """Create a payment intent for subscription payment"""
        try:
            # Get or create Stripe customer
            if not hasattr(user, 'subscription') or not user.subscription.stripe_customer_id:
                customer_result = self.stripe_service.create_customer(user)
                if not customer_result['success']:
                    return error_response(f"Failed to create customer: {customer_result['error']}")
                
                customer_id = customer_result['data']['customer_id']
                
                # Update user subscription with customer ID
                if hasattr(user, 'subscription'):
                    user.subscription.stripe_customer_id = customer_id
                    user.subscription.save()
            else:
                customer_id = user.subscription.stripe_customer_id
            
            # Create payment intent
            intent_result = self.stripe_service.create_payment_intent(
                amount=amount,
                currency=currency,
                customer_id=customer_id,
                payment_method_id=payment_method_id
            )
            
            if not intent_result['success']:
                return error_response(f"Failed to create payment intent: {intent_result['error']}")
            
            payment_intent = intent_result['data']['payment_intent']
            
            return success_response(
                "Payment intent created successfully",
                data={
                    'payment_intent_id': payment_intent.id,
                    'client_secret': payment_intent.client_secret,
                    'amount': amount,
                    'currency': currency,
                    'status': payment_intent.status
                }
            )
            
        except Exception as e:
            logger.error(f"Payment intent creation failed: {str(e)}")
            return error_response(f"Failed to create payment intent: {str(e)}")
    
    def process_subscription_payment(self, user, subscription_id, payment_method_id=None, promo_code=None):
        """Process payment for a subscription with all payment types and promo codes"""
        try:
            # Get user subscription
            try:
                subscription = UserSubscription.objects.get(
                    id=subscription_id, 
                    user=user
                )
            except UserSubscription.DoesNotExist:
                return error_response("Subscription not found", status_code=404)
            
            # Get payment method
            if payment_method_id:
                try:
                    payment_method = PaymentMethod.objects.get(
                        id=payment_method_id, 
                        user=user,
                        is_active=True
                    )
                except PaymentMethod.DoesNotExist:
                    return error_response("Payment method not found", status_code=404)
            else:
                # Use default payment method
                try:
                    payment_method = PaymentMethod.objects.get(
                        user=user, 
                        is_default=True,
                        is_active=True
                    )
                except PaymentMethod.DoesNotExist:
                    return error_response("No default payment method found", status_code=400)
            
            # Validate payment method
            if not payment_method.is_valid():
                return error_response("Payment method is expired or inactive", status_code=400)
            
            # Calculate final amount (with promo code if provided)
            final_amount = subscription.plan.price
            discount_applied = 0
            promo_code_used = None
            
            if promo_code:
                promo_result = self._apply_promo_code(subscription.plan, promo_code, user)
                if not promo_result.get('success', False):
                    return error_response(
                        promo_result.get('message', 'Promo code validation failed'),
                        status_code=promo_result.get('status_code', 400)
                    )
                
                final_amount = promo_result['data']['final_amount']
                discount_applied = promo_result['data']['discount_applied']
                promo_code_used = promo_code
            
            # Process payment based on payment method type
            if payment_method.type == 'card':
                return self._process_card_subscription_payment(
                    user, subscription, payment_method, final_amount, discount_applied, promo_code_used
                )
            elif payment_method.type == 'apple_pay':
                return self._process_apple_pay_subscription_payment(
                    user, subscription, payment_method, final_amount, discount_applied, promo_code_used
                )
            elif payment_method.type == 'google_pay':
                return self._process_google_pay_subscription_payment(
                    user, subscription, payment_method, final_amount, discount_applied, promo_code_used
                )
            else:
                return error_response("Unsupported payment method type", status_code=400)
            
        except Exception as e:
            logger.error(f"Subscription payment processing failed: {str(e)}")
            return error_response(f"Failed to process subscription payment: {str(e)}")
    
    def _apply_promo_code(self, plan, promo_code, user):
        """Apply promo code and calculate discount"""
        try:
            from ..models import PromoCode
            
            # Get promo code
            try:
                promo = PromoCode.objects.get(code=promo_code)
            except PromoCode.DoesNotExist:
                return {
                    'success': False,
                    'message': "Invalid promo code",
                    'status_code': 400
                }
            
            # Validate promo code
            if not promo.is_valid():
                return {
                    'success': False,
                    'message': "Promo code is expired or inactive",
                    'status_code': 400
                }
            
            # Check if user already used this code
            if not promo.can_be_used_by_user(user):
                return {
                    'success': False,
                    'message': "You have already used this promo code",
                    'status_code': 400
                }
            
            # Calculate discount
            from decimal import Decimal
            plan_price = Decimal(str(plan.price))
            promo_value = Decimal(str(promo.discount_value))
            
            if promo.discount_type == 'percentage':
                discount_amount = plan_price * (promo_value / 100)
            else:  # fixed amount
                discount_amount = promo_value
            
            # Ensure discount doesn't exceed original price
            discount_amount = min(discount_amount, plan_price)
            final_amount = plan_price - discount_amount
            
            return {
                'success': True,
                'message': "Promo code applied successfully",
                'data': {
                    'original_amount': float(plan.price),
                    'discount_applied': float(discount_amount),
                    'final_amount': float(final_amount),
                    'promo_code': promo.code
                }
            }
            
        except Exception as e:
            logger.error(f"Promo code application failed: {str(e)}")
            return {
                'success': False,
                'message': f"Failed to apply promo code: {str(e)}",
                'status_code': 500
            }
    
    def _process_card_subscription_payment(self, user, subscription, payment_method, final_amount, discount_applied, promo_code_used):
        """Process card subscription payment via Stripe"""
        try:
            # Create Stripe subscription
            subscription_result = self.stripe_service.create_subscription(
                customer_id=subscription.stripe_customer_id,
                price_id=subscription.plan.stripe_price_id,
                payment_method_id=payment_method.stripe_payment_method_id,
                trial_period_days=subscription.plan.trial_days
            )
            
            if not subscription_result['success']:
                return error_response(f"Failed to create Stripe subscription: {subscription_result['error']}")
            
            stripe_subscription = subscription_result['data']['subscription']
            
            print(f"Stripe subscription created: {stripe_subscription.id}")
            print(f"Stripe subscription status: {stripe_subscription.status}")
            
            # Update local subscription with promo code details
            subscription.stripe_subscription_id = stripe_subscription.id
            subscription.status = 'trialing' if subscription.plan.trial_days > 0 else 'active'
            subscription.promo_code_used = promo_code_used
            subscription.discount_applied = discount_applied
            subscription.original_amount = subscription.plan.price
            subscription.save()
            
            # Create subscription history
            from ..models import SubscriptionHistory
            SubscriptionHistory.objects.create(
                subscription=subscription,
                event_type='created',
                description=f"Subscription created with Stripe ID: {stripe_subscription.id}",
                metadata={
                    'stripe_subscription_id': stripe_subscription.id,
                    'final_amount': float(final_amount),
                    'discount_applied': float(discount_applied),
                    'promo_code_used': promo_code_used
                }
            )
            
            # Get payment intent ID and confirm payment
            payment_intent_id = None
            transaction_status = 'pending'
            
            try:
                print(f"Processing subscription with status: {stripe_subscription.status}")
                
                # For incomplete subscriptions, we need to retrieve the latest invoice
                if stripe_subscription.status == 'incomplete':
                    print("Subscription is incomplete, retrieving expanded data...")
                    # Retrieve the subscription with expanded invoice data
                    expanded_subscription = stripe.Subscription.retrieve(
                        stripe_subscription.id,
                        expand=['latest_invoice.payment_intent']
                    )
                    
                    print(f"Expanded subscription status: {expanded_subscription.status}")
                    print(f"Has latest_invoice: {hasattr(expanded_subscription, 'latest_invoice')}")
                    
                    if (hasattr(expanded_subscription, 'latest_invoice') and 
                        expanded_subscription.latest_invoice):
                        
                        latest_invoice = expanded_subscription.latest_invoice
                        print(f"Latest invoice ID: {latest_invoice.id}")
                        print(f"Latest invoice status: {latest_invoice.status}")
                        
                        # Check if payment intent exists
                        if hasattr(latest_invoice, 'payment_intent') and latest_invoice.payment_intent:
                            payment_intent_id = latest_invoice.payment_intent.id
                            print(f"Found payment intent ID: {payment_intent_id}")
                            
                            # Automatically confirm the payment intent
                            try:
                                confirmed_intent = stripe.PaymentIntent.confirm(payment_intent_id)
                                print(f"Payment intent confirmed: {confirmed_intent.status}")
                                
                                # Update transaction status based on confirmation
                                if confirmed_intent.status == 'succeeded':
                                    transaction_status = 'succeeded'
                                    subscription.status = 'active'
                                    subscription.save()
                                    print("Subscription activated due to successful payment")
                                else:
                                    transaction_status = 'pending'
                                    print(f"Payment intent status: {confirmed_intent.status}")
                                    
                            except stripe.error.StripeError as e:
                                print(f"Failed to confirm payment intent: {str(e)}")
                                transaction_status = 'pending'
                        else:
                            print("No payment intent in latest invoice, waiting for webhook...")
                            # The payment intent will be created via webhook
                            # We'll update the transaction when webhook processes it
                            transaction_status = 'pending'
                    else:
                        print("No latest invoice found in expanded subscription")
                        transaction_status = 'pending'
                else:
                    print(f"Subscription status is not incomplete: {stripe_subscription.status}")
                    if stripe_subscription.status == 'active':
                        transaction_status = 'succeeded'
                        print("Subscription is already active")
                    else:
                        transaction_status = 'pending'
                        print(f"Subscription status: {stripe_subscription.status}")
                        
            except (AttributeError, TypeError) as e:
                print(f"Error processing subscription: {str(e)}")
                payment_intent_id = None
                transaction_status = 'pending'
            
            # Transaction status is already determined above based on payment confirmation
            
            # Create payment transaction record
            transaction = PaymentTransaction.objects.create(
                user=user,
                subscription=subscription,
                payment_method=payment_method,
                transaction_id=str(uuid.uuid4()),
                amount=final_amount,
                currency='USD',
                status=transaction_status,
                payment_method_type='stripe',
                stripe_payment_intent_id=payment_intent_id,  # Will be updated by webhook if None
                promo_code_used=promo_code_used,
                discount_applied=discount_applied,
                original_amount=subscription.plan.price
            )
            
            print(f"Created transaction {transaction.id} with status: {transaction_status}")
            if payment_intent_id:
                print(f"Transaction linked to payment intent: {payment_intent_id}")
            else:
                print("Transaction created without payment intent - will be updated by webhook")
            
            # Increment promo code usage if used
            if promo_code_used:
                from ..models import PromoCode
                try:
                    promo = PromoCode.objects.get(code=promo_code_used)
                    promo.used_count += 1
                    promo.save()
                except PromoCode.DoesNotExist:
                    pass
            
            return success_response(
                "Card subscription payment processed successfully",
                data={
                    'subscription_id': subscription.id,
                    'stripe_subscription_id': stripe_subscription.id,
                    'status': subscription.status,
                    'transaction_id': transaction.transaction_id,
                    'final_amount': float(final_amount),
                    'discount_applied': float(discount_applied)
                }
            )
            
        except Exception as e:
            logger.error(f"Card subscription payment processing failed: {str(e)}")
            return error_response(f"Failed to process card subscription payment: {str(e)}")
    
    def _process_apple_pay_subscription_payment(self, user, subscription, payment_method, final_amount, discount_applied, promo_code_used):
        """Process Apple Pay subscription payment using Stripe"""
        try:
            # Create Stripe subscription using the Apple Pay payment method
            subscription_result = self.stripe_service.create_subscription(
                customer_id=subscription.stripe_customer_id,
                price_id=subscription.plan.stripe_price_id,
                payment_method_id=payment_method.stripe_payment_method_id,
                trial_period_days=subscription.plan.trial_days
            )
            
            if not subscription_result['success']:
                return error_response(f"Failed to create Stripe subscription: {subscription_result['error']}")
            
            stripe_subscription = subscription_result['data']['subscription']
            
            # Update local subscription with promo code details
            subscription.stripe_subscription_id = stripe_subscription.id
            subscription.status = 'trialing' if subscription.plan.trial_days > 0 else 'active'
            subscription.promo_code_used = promo_code_used
            subscription.discount_applied = discount_applied
            subscription.original_amount = subscription.plan.price
            subscription.save()
            
            # Create subscription history
            from ..models import SubscriptionHistory
            SubscriptionHistory.objects.create(
                subscription=subscription,
                event_type='created',
                description=f"Apple Pay subscription created with Stripe ID: {stripe_subscription.id}",
                metadata={
                    'stripe_subscription_id': stripe_subscription.id,
                    'final_amount': float(final_amount),
                    'discount_applied': float(discount_applied),
                    'promo_code_used': promo_code_used
                }
            )
            
            # Get payment intent ID and confirm payment
            payment_intent_id = None
            transaction_status = 'pending'
            
            try:
                # For incomplete subscriptions, retrieve the latest invoice
                if stripe_subscription.status == 'incomplete':
                    expanded_subscription = stripe.Subscription.retrieve(
                        stripe_subscription.id,
                        expand=['latest_invoice.payment_intent']
                    )
                    
                    if (hasattr(expanded_subscription, 'latest_invoice') and 
                        expanded_subscription.latest_invoice):
                        
                        latest_invoice = expanded_subscription.latest_invoice
                        
                        if hasattr(latest_invoice, 'payment_intent') and latest_invoice.payment_intent:
                            payment_intent_id = latest_invoice.payment_intent.id
                            
                            # Automatically confirm the payment intent
                            try:
                                confirmed_intent = stripe.PaymentIntent.confirm(payment_intent_id)
                                
                                if confirmed_intent.status == 'succeeded':
                                    transaction_status = 'succeeded'
                                    subscription.status = 'active'
                                    subscription.save()
                                else:
                                    transaction_status = 'pending'
                                    
                            except stripe.error.StripeError as e:
                                logger.warning(f"Failed to confirm payment intent: {str(e)}")
                                transaction_status = 'pending'
                        else:
                            transaction_status = 'pending'
                    else:
                        transaction_status = 'pending'
                else:
                    if stripe_subscription.status == 'active':
                        transaction_status = 'succeeded'
                    else:
                        transaction_status = 'pending'
                        
            except (AttributeError, TypeError) as e:
                logger.warning(f"Error processing subscription: {str(e)}")
                payment_intent_id = None
                transaction_status = 'pending'
            
            # Create payment transaction record
            transaction = PaymentTransaction.objects.create(
                user=user,
                subscription=subscription,
                payment_method=payment_method,
                transaction_id=str(uuid.uuid4()),
                amount=final_amount,
                currency='USD',
                status=transaction_status,
                payment_method_type='stripe',  # Use 'stripe' since it's processed through Stripe
                stripe_payment_intent_id=payment_intent_id,
                apple_pay_token=payment_method.apple_pay_token,
                promo_code_used=promo_code_used,
                discount_applied=discount_applied,
                original_amount=subscription.plan.price
            )
            
            # Increment promo code usage if used
            if promo_code_used:
                from ..models import PromoCode
                try:
                    promo = PromoCode.objects.get(code=promo_code_used)
                    promo.used_count += 1
                    promo.save()
                except PromoCode.DoesNotExist:
                    pass
            
            return success_response(
                "Apple Pay subscription payment processed successfully",
                data={
                    'subscription_id': subscription.id,
                    'stripe_subscription_id': stripe_subscription.id,
                    'status': subscription.status,
                    'transaction_id': transaction.transaction_id,
                    'final_amount': float(final_amount),
                    'discount_applied': float(discount_applied)
                }
            )
            
        except Exception as e:
            logger.error(f"Apple Pay subscription payment processing failed: {str(e)}")
            return error_response(f"Failed to process Apple Pay subscription payment: {str(e)}")
    
    def _process_google_pay_subscription_payment(self, user, subscription, payment_method, final_amount, discount_applied, promo_code_used):
        """Process Google Pay subscription payment using Stripe"""
        try:
            # Create Stripe subscription using the Google Pay payment method
            subscription_result = self.stripe_service.create_subscription(
                customer_id=subscription.stripe_customer_id,
                price_id=subscription.plan.stripe_price_id,
                payment_method_id=payment_method.stripe_payment_method_id,
                trial_period_days=subscription.plan.trial_days
            )
            
            if not subscription_result['success']:
                return error_response(f"Failed to create Stripe subscription: {subscription_result['error']}")
            
            stripe_subscription = subscription_result['data']['subscription']
            
            # Update local subscription with promo code details
            subscription.stripe_subscription_id = stripe_subscription.id
            subscription.status = 'trialing' if subscription.plan.trial_days > 0 else 'active'
            subscription.promo_code_used = promo_code_used
            subscription.discount_applied = discount_applied
            subscription.original_amount = subscription.plan.price
            subscription.save()
            
            # Create subscription history
            from ..models import SubscriptionHistory
            SubscriptionHistory.objects.create(
                subscription=subscription,
                event_type='created',
                description=f"Google Pay subscription created with Stripe ID: {stripe_subscription.id}",
                metadata={
                    'stripe_subscription_id': stripe_subscription.id,
                    'final_amount': float(final_amount),
                    'discount_applied': float(discount_applied),
                    'promo_code_used': promo_code_used
                }
            )
            
            # Get payment intent ID and confirm payment
            payment_intent_id = None
            transaction_status = 'pending'
            
            try:
                # For incomplete subscriptions, retrieve the latest invoice
                if stripe_subscription.status == 'incomplete':
                    expanded_subscription = stripe.Subscription.retrieve(
                        stripe_subscription.id,
                        expand=['latest_invoice.payment_intent']
                    )
                    
                    if (hasattr(expanded_subscription, 'latest_invoice') and 
                        expanded_subscription.latest_invoice):
                        
                        latest_invoice = expanded_subscription.latest_invoice
                        
                        if hasattr(latest_invoice, 'payment_intent') and latest_invoice.payment_intent:
                            payment_intent_id = latest_invoice.payment_intent.id
                            
                            # Automatically confirm the payment intent
                            try:
                                confirmed_intent = stripe.PaymentIntent.confirm(payment_intent_id)
                                
                                if confirmed_intent.status == 'succeeded':
                                    transaction_status = 'succeeded'
                                    subscription.status = 'active'
                                    subscription.save()
                                else:
                                    transaction_status = 'pending'
                                    
                            except stripe.error.StripeError as e:
                                logger.warning(f"Failed to confirm payment intent: {str(e)}")
                                transaction_status = 'pending'
                        else:
                            transaction_status = 'pending'
                    else:
                        transaction_status = 'pending'
                else:
                    if stripe_subscription.status == 'active':
                        transaction_status = 'succeeded'
                    else:
                        transaction_status = 'pending'
                        
            except (AttributeError, TypeError) as e:
                logger.warning(f"Error processing subscription: {str(e)}")
                payment_intent_id = None
                transaction_status = 'pending'
            
            # Create payment transaction record
            transaction = PaymentTransaction.objects.create(
                user=user,
                subscription=subscription,
                payment_method=payment_method,
                transaction_id=str(uuid.uuid4()),
                amount=final_amount,
                currency='USD',
                status=transaction_status,
                payment_method_type='stripe',  # Use 'stripe' since it's processed through Stripe
                stripe_payment_intent_id=payment_intent_id,
                google_pay_token=payment_method.google_pay_token,
                promo_code_used=promo_code_used,
                discount_applied=discount_applied,
                original_amount=subscription.plan.price
            )
            
            # Increment promo code usage if used
            if promo_code_used:
                from ..models import PromoCode
                try:
                    promo = PromoCode.objects.get(code=promo_code_used)
                    promo.used_count += 1
                    promo.save()
                except PromoCode.DoesNotExist:
                    pass
            
            return success_response(
                "Google Pay subscription payment processed successfully",
                data={
                    'subscription_id': subscription.id,
                    'stripe_subscription_id': stripe_subscription.id,
                    'status': subscription.status,
                    'transaction_id': transaction.transaction_id,
                    'final_amount': float(final_amount),
                    'discount_applied': float(discount_applied)
                }
            )
            
        except Exception as e:
            logger.error(f"Google Pay subscription payment processing failed: {str(e)}")
            return error_response(f"Failed to process Google Pay subscription payment: {str(e)}")
    
    def process_apple_pay(self, user, payment_token, amount, currency='USD', subscription_id=None):
        """Process Apple Pay payment"""
        try:
            # Generate transaction ID
            transaction_id = f"apple_{uuid.uuid4().hex[:16]}"
            
            # Create payment transaction record
            payment_transaction = PaymentTransaction.objects.create(
                user=user,
                transaction_id=transaction_id,
                amount=amount,
                currency=currency,
                status='pending',
                payment_method_type='apple_pay',
                apple_pay_token=payment_token,
                metadata={'subscription_id': subscription_id}
            )
            
            # TODO: Implement actual Apple Pay validation when credentials are available
            # For now, simulate successful payment
            payment_transaction.status = 'succeeded'
            payment_transaction.save()
            
            return success_response(
                "Apple Pay payment processed successfully (demo mode)",
                data={
                    'transaction_id': transaction_id,
                    'status': 'succeeded'
                }
            )
            
        except Exception as e:
            logger.error(f"Apple Pay payment processing failed: {str(e)}")
            return error_response(f"Failed to process Apple Pay payment: {str(e)}")
    
    def process_google_pay(self, user, payment_token, amount, currency='USD', subscription_id=None):
        """Process Google Pay payment"""
        try:
            # Generate transaction ID
            transaction_id = f"google_{uuid.uuid4().hex[:16]}"
            
            # Create payment transaction record
            payment_transaction = PaymentTransaction.objects.create(
                user=user,
                transaction_id=transaction_id,
                amount=amount,
                currency=currency,
                status='pending',
                payment_method_type='google_pay',
                google_pay_token=payment_token,
                metadata={'subscription_id': subscription_id}
            )
            
            # TODO: Implement actual Google Pay validation when credentials are available
            # For now, simulate successful payment
            payment_transaction.status = 'succeeded'
            payment_transaction.save()
            
            return success_response(
                "Google Pay payment processed successfully (demo mode)",
                data={
                    'transaction_id': transaction_id,
                    'status': 'succeeded'
                }
            )
            
        except Exception as e:
            logger.error(f"Google Pay payment processing failed: {str(e)}")
            return error_response(f"Failed to process Google Pay payment: {str(e)}")
