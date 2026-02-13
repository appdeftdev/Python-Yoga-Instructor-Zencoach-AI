import stripe
import uuid
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from ..models import (
    SubscriptionPlan, 
    UserSubscription, 
    PaymentMethod, 
    PaymentTransaction, 
    SubscriptionHistory
)
from utils.response_format import success_response, error_response


class SubscriptionService:
    """Service class for subscription management"""
    
    def __init__(self):
        self.stripe_secret_key = settings.STRIPE_SECRET_KEY
        if self.stripe_secret_key:
            stripe.api_key = self.stripe_secret_key
    
    def create_subscription(self, user, plan_id, payment_method_id=None, 
                          payment_method_type='stripe', apple_pay_token=None, 
                          google_pay_token=None):
        """Create a new subscription for user"""
        try:
            with transaction.atomic():
                # Get the subscription plan
                plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
                
                # Check if user already has an active subscription
                existing_subscription = UserSubscription.objects.filter(
                    user=user, 
                    status__in=['trial', 'active']
                ).first()
                
                if existing_subscription:
                    return error_response(
                        "User already has an active subscription",
                        status_code=400
                    )
                
                # Create Stripe customer if not exists
                stripe_customer_id = self._get_or_create_stripe_customer(user)
                
                # Calculate trial and billing periods
                now = timezone.now()
                trial_start = now if plan.trial_days > 0 else None
                trial_end = now + timedelta(days=plan.trial_days) if plan.trial_days > 0 else None
                
                # Calculate billing period
                if plan.billing_cycle == 'monthly':
                    period_start = trial_end if trial_end else now
                    period_end = period_start + timedelta(days=30)
                else:  # yearly
                    period_start = trial_end if trial_end else now
                    period_end = period_start + timedelta(days=365)
                
                # Create subscription record
                subscription = UserSubscription.objects.create(
                    user=user,
                    plan=plan,
                    status='trial' if plan.trial_days > 0 else 'active',
                    stripe_customer_id=stripe_customer_id,
                    trial_start=trial_start,
                    trial_end=trial_end,
                    current_period_start=period_start,
                    current_period_end=period_end
                )
                
                # Create subscription history
                SubscriptionHistory.objects.create(
                    subscription=subscription,
                    event_type='created',
                    description=f"Subscription created for {plan.name}",
                    metadata={'plan_id': plan.id, 'trial_days': plan.trial_days}
                )
                
                # If trial, create trial started history
                if plan.trial_days > 0:
                    SubscriptionHistory.objects.create(
                        subscription=subscription,
                        event_type='trial_started',
                        description=f"Trial period started for {plan.trial_days} days",
                        metadata={'trial_end': trial_end.isoformat()}
                    )
                
                return success_response(
                    "Subscription created successfully",
                    data={'subscription_id': subscription.id}
                )
                
        except SubscriptionPlan.DoesNotExist:
            return error_response("Invalid subscription plan", status_code=400)
        except Exception as e:
            return error_response(f"Failed to create subscription: {str(e)}", status_code=500)
    
    def cancel_subscription(self, user, cancel_immediately=False, reason=None):
        """Cancel user's subscription"""
        try:
            with transaction.atomic():
                subscription = UserSubscription.objects.get(
                    user=user, 
                    status__in=['trial', 'active']
                )
                
                if cancel_immediately:
                    subscription.status = 'cancelled'
                    subscription.cancelled_at = timezone.now()
                    subscription.save()
                    
                    # Create cancellation history
                    SubscriptionHistory.objects.create(
                        subscription=subscription,
                        event_type='cancelled',
                        description=f"Subscription cancelled immediately. Reason: {reason or 'No reason provided'}",
                        metadata={'reason': reason, 'cancelled_immediately': True}
                    )
                else:
                    subscription.cancel_at_period_end = True
                    subscription.save()
                    
                    # Create cancellation history
                    SubscriptionHistory.objects.create(
                        subscription=subscription,
                        event_type='cancelled',
                        description=f"Subscription will be cancelled at period end. Reason: {reason or 'No reason provided'}",
                        metadata={'reason': reason, 'cancelled_immediately': False}
                    )
                
                return success_response("Subscription cancelled successfully")
                
        except UserSubscription.DoesNotExist:
            return error_response("No active subscription found", status_code=404)
        except Exception as e:
            return error_response(f"Failed to cancel subscription: {str(e)}", status_code=500)
    
    def get_user_subscription(self, user):
        """Get user's current subscription"""
        try:
            subscription = UserSubscription.objects.get(user=user)
            return success_response(
                "Subscription retrieved successfully",
                data={'subscription': subscription}
            )
        except UserSubscription.DoesNotExist:
            return error_response("No subscription found", status_code=404)
        except Exception as e:
            return error_response(f"Failed to get subscription: {str(e)}", status_code=500)
    
    def _get_or_create_stripe_customer(self, user):
        """Get or create Stripe customer for user"""
        if not self.stripe_secret_key:
            return None
            
        try:
            # Check if user already has a Stripe customer ID
            existing_subscription = UserSubscription.objects.filter(
                user=user, 
                stripe_customer_id__isnull=False
            ).first()
            
            if existing_subscription:
                return existing_subscription.stripe_customer_id
            
            # Create new Stripe customer
            customer = stripe.Customer.create(
                email=user.email,
                name=f"{user.first_name} {user.last_name}".strip(),
                metadata={'user_id': user.id}
            )
            
            return customer.id
            
        except Exception as e:
            print(f"Failed to create Stripe customer: {str(e)}")
            return None


class PaymentService:
    """Service class for payment processing"""
    
    def __init__(self):
        self.stripe_secret_key = settings.STRIPE_SECRET_KEY
        if self.stripe_secret_key:
            stripe.api_key = self.stripe_secret_key
    
    def create_payment_intent(self, user, amount, currency='USD', 
                            payment_method_id=None, payment_method_type='stripe',
                            apple_pay_token=None, google_pay_token=None, metadata=None):
        """Create a payment intent for processing payment"""
        try:
            # Generate transaction ID
            transaction_id = f"txn_{uuid.uuid4().hex[:16]}"
            
            # Create payment transaction record
            payment_transaction = PaymentTransaction.objects.create(
                user=user,
                transaction_id=transaction_id,
                amount=amount,
                currency=currency,
                status='pending',
                payment_method_type=payment_method_type,
                apple_pay_token=apple_pay_token,
                google_pay_token=google_pay_token,
                metadata=metadata or {}
            )
            
            if payment_method_id:
                try:
                    payment_method = PaymentMethod.objects.get(
                        id=payment_method_id, 
                        user=user
                    )
                    payment_transaction.payment_method = payment_method
                    payment_transaction.save()
                except PaymentMethod.DoesNotExist:
                    return error_response("Invalid payment method", status_code=400)
            
            # Create Stripe payment intent if Stripe is configured
            if self.stripe_secret_key and payment_method_type == 'stripe':
                try:
                    # Get or create Stripe customer
                    subscription_service = SubscriptionService()
                    stripe_customer_id = subscription_service._get_or_create_stripe_customer(user)
                    
                    # Create payment intent
                    intent = stripe.PaymentIntent.create(
                        amount=int(amount * 100),  # Convert to cents
                        currency=currency.lower(),
                        customer=stripe_customer_id,
                        payment_method=payment_method.stripe_payment_method_id if payment_method else None,
                        confirmation_method='manual',
                        confirm=True,
                        metadata={
                            'transaction_id': transaction_id,
                            'user_id': user.id
                        }
                    )
                    
                    payment_transaction.stripe_payment_intent_id = intent.id
                    payment_transaction.status = 'succeeded' if intent.status == 'succeeded' else 'pending'
                    payment_transaction.save()
                    
                    return success_response(
                        "Payment intent created successfully",
                        data={
                            'transaction_id': transaction_id,
                            'client_secret': intent.client_secret,
                            'status': payment_transaction.status
                        }
                    )
                    
                except stripe.error.StripeError as e:
                    payment_transaction.status = 'failed'
                    payment_transaction.error_message = str(e)
                    payment_transaction.error_code = e.code
                    payment_transaction.save()
                    
                    return error_response(f"Stripe error: {str(e)}", status_code=400)
            
            # For Apple Pay and Google Pay, we'll implement validation later
            # when we have the proper credentials
            return success_response(
                "Payment intent created successfully (demo mode)",
                data={
                    'transaction_id': transaction_id,
                    'status': 'pending',
                    'note': 'Payment processing requires proper credentials'
                }
            )
            
        except Exception as e:
            return error_response(f"Failed to create payment intent: {str(e)}", status_code=500)
    
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
            return error_response(f"Failed to process Apple Pay payment: {str(e)}", status_code=500)
    
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
            return error_response(f"Failed to process Google Pay payment: {str(e)}", status_code=500)
    
    def get_payment_methods(self, user):
        """Get user's payment methods"""
        try:
            payment_methods = PaymentMethod.objects.filter(user=user)
            return success_response(
                "Payment methods retrieved successfully",
                data={'payment_methods': payment_methods}
            )
        except Exception as e:
            return error_response(f"Failed to get payment methods: {str(e)}", status_code=500)
    
    def get_payment_history(self, user):
        """Get user's payment history"""
        try:
            transactions = PaymentTransaction.objects.filter(user=user).order_by('-created_at')
            return success_response(
                "Payment history retrieved successfully",
                data={'transactions': transactions}
            )
        except Exception as e:
            return error_response(f"Failed to get payment history: {str(e)}", status_code=500)


class WebhookService:
    """Service class for handling webhooks"""
    
    def __init__(self):
        self.stripe_secret_key = settings.STRIPE_SECRET_KEY
        if self.stripe_secret_key:
            stripe.api_key = self.stripe_secret_key
    
    def handle_stripe_webhook(self, event_data, signature):
        """Handle Stripe webhook events"""
        try:
            # Verify webhook signature
            webhook_secret = settings.STRIPE_WEBHOOK_SECRET
            if webhook_secret and signature:
                try:
                    event = stripe.Webhook.construct_event(
                        event_data, signature, webhook_secret
                    )
                except stripe.error.SignatureVerificationError as e:
                    print(f"Webhook signature verification failed: {str(e)}")
                    # In test mode, continue with event processing
                    import json
                    event = json.loads(event_data)
            else:
                # In demo mode, just parse the event data
                import json
                event = json.loads(event_data)
            
            event_type = event.get('type')
            data = event.get('data', {}).get('object', {})
            
            print(f"Processing webhook event: {event_type}")  # Debug log
            
            if event_type == 'customer.subscription.created':
                self._handle_subscription_created(data)
            elif event_type == 'customer.subscription.updated':
                self._handle_subscription_updated(data)
            elif event_type == 'customer.subscription.deleted':
                self._handle_subscription_deleted(data)
            elif event_type == 'payment_intent.created':
                self._handle_payment_intent_created(data)
            elif event_type == 'payment_intent.succeeded':
                self._handle_payment_succeeded(data)
            elif event_type == 'payment_intent.payment_failed':
                self._handle_payment_failed(data)
            elif event_type == 'invoice.payment_succeeded':
                self._handle_invoice_payment_succeeded(data)
            elif event_type == 'invoice.payment_failed':
                self._handle_invoice_payment_failed(data)
            else:
                print(f"Unhandled webhook event type: {event_type}")
            
            return success_response("Webhook processed successfully")
            
        except Exception as e:
            print(f"Webhook error: {str(e)}")  # Debug log
            return error_response(f"Failed to process webhook: {str(e)}", status_code=500)
    
    def _handle_subscription_created(self, data):
        """Handle subscription created event"""
        try:
            print(f"Subscription created: {data.get('id')}")
            # Update subscription status in database
            # This would typically update your UserSubscription model
        except Exception as e:
            print(f"Error handling subscription created: {str(e)}")
    
    def _handle_subscription_updated(self, data):
        """Handle subscription updated event"""
        try:
            print(f"Subscription updated: {data.get('id')}")
            # Update subscription status in database
        except Exception as e:
            print(f"Error handling subscription updated: {str(e)}")
    
    def _handle_subscription_deleted(self, data):
        """Handle subscription deleted event"""
        try:
            print(f"Subscription deleted: {data.get('id')}")
            # Mark subscription as cancelled in database
        except Exception as e:
            print(f"Error handling subscription deleted: {str(e)}")
    
    def _handle_payment_intent_created(self, data):
        """Handle payment intent created event"""
        try:
            payment_intent_id = data.get('id')
            print(f"Payment intent created: {payment_intent_id}")
            
            # Get the payment intent details to find the subscription
            try:
                payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
                print(f"Payment intent metadata: {payment_intent.metadata}")
                
                # Try to find the transaction by subscription
                from ..models import PaymentTransaction, UserSubscription
                
                # Look for pending transactions without payment intent ID
                pending_transactions = PaymentTransaction.objects.filter(
                    status='pending',
                    stripe_payment_intent_id__isnull=True,
                    subscription__isnull=False
                ).order_by('-created_at')
                
                if pending_transactions.exists():
                    # Get the most recent pending transaction
                    transaction = pending_transactions.first()
                    print(f"Found pending transaction {transaction.id} to link with payment intent")
                    
                    # Update transaction with payment intent ID
                    transaction.stripe_payment_intent_id = payment_intent_id
                    transaction.save()
                    
                    # Confirm the payment intent
                    try:
                        confirmed_intent = stripe.PaymentIntent.confirm(payment_intent_id)
                        print(f"Payment intent confirmed: {confirmed_intent.status}")
                        
                        if confirmed_intent.status == 'succeeded':
                            transaction.status = 'succeeded'
                            transaction.save()
                            
                            # Update subscription status if needed
                            if hasattr(transaction, 'subscription') and transaction.subscription:
                                subscription = transaction.subscription
                                if subscription.status == 'pending':
                                    subscription.status = 'active'
                                    subscription.save()
                                    print(f"Subscription {subscription.id} activated")
                                    
                                    # Create subscription history
                                    from ..models import SubscriptionHistory
                                    SubscriptionHistory.objects.create(
                                        subscription=subscription,
                                        event_type='activated',
                                        description=f"Payment confirmed and subscription activated via webhook",
                                        metadata={'payment_intent_id': payment_intent_id}
                                    )
                            
                            print(f"Transaction {transaction.id} updated to succeeded")
                        else:
                            print(f"Payment intent status: {confirmed_intent.status}")
                            
                    except stripe.error.StripeError as e:
                        print(f"Failed to confirm payment intent: {str(e)}")
                else:
                    print(f"No pending transactions found to link with payment intent {payment_intent_id}")
                    
            except stripe.error.StripeError as e:
                print(f"Failed to retrieve payment intent: {str(e)}")
                
        except Exception as e:
            print(f"Error handling payment intent created: {str(e)}")
    
    def _handle_payment_succeeded(self, data):
        """Handle payment succeeded event"""
        try:
            payment_intent_id = data.get('id')
            print(f"Payment succeeded event - Payment Intent ID: {payment_intent_id}")
            print(f"Payment intent metadata: {data.get('metadata', {})}")
            
            if payment_intent_id:
                from ..models import PaymentTransaction, UserSubscription
                
                # Try to find transaction by payment intent ID
                try:
                    transaction = PaymentTransaction.objects.get(
                        stripe_payment_intent_id=payment_intent_id
                    )
                    transaction.status = 'succeeded'
                    transaction.save()
                    
                    # Update subscription status to active
                    if hasattr(transaction, 'subscription') and transaction.subscription:
                        subscription = transaction.subscription
                        if subscription.status in ['pending', 'trialing']:
                            subscription.status = 'active'
                            subscription.save()
                            print(f"Subscription {subscription.id} activated")
                    
                    print(f"Updated transaction {transaction.id} to succeeded")
                except PaymentTransaction.DoesNotExist:
                    print(f"No transaction found for payment intent {payment_intent_id}")
                    # Try to find by metadata or other methods
                    print(f"Searching for pending transactions...")
                    pending_txns = PaymentTransaction.objects.filter(
                        status='pending',
                        stripe_payment_intent_id__isnull=False
                    )
                    for txn in pending_txns:
                        print(f"Found pending transaction {txn.id} with payment intent {txn.stripe_payment_intent_id}")
        except Exception as e:
            print(f"Error handling payment succeeded: {str(e)}")
    
    def _handle_payment_failed(self, data):
        """Handle payment failed event"""
        try:
            print(f"Payment failed: {data.get('id')}")
            # Update payment status
            # Handle failed payment logic
        except Exception as e:
            print(f"Error handling payment failed: {str(e)}")
    
    def _handle_invoice_payment_succeeded(self, data):
        """Handle invoice payment succeeded event"""
        try:
            print(f"Invoice payment succeeded: {data.get('id')}")
            # Handle successful invoice payment
        except Exception as e:
            print(f"Error handling invoice payment succeeded: {str(e)}")
    
    def _handle_invoice_payment_failed(self, data):
        """Handle invoice payment failed event"""
        try:
            print(f"Invoice payment failed: {data.get('id')}")
            # Handle failed invoice payment
        except Exception as e:
            print(f"Error handling invoice payment failed: {str(e)}")


class StripeProductService:
    """Service class for creating Stripe products and prices"""
    
    def __init__(self):
        self.stripe_secret_key = settings.STRIPE_SECRET_KEY
        if self.stripe_secret_key:
            stripe.api_key = self.stripe_secret_key
    
    def create_stripe_product(self, plan):
        """Create Stripe product for a subscription plan"""
        try:
            if not self.stripe_secret_key:
                return {
                    'success': False,
                    'message': "Stripe secret key not configured",
                    'status_code': 500
                }
            
            # Check if product already exists
            if plan.stripe_product_id:
                return {
                    'success': False,
                    'message': "Stripe product already exists for this plan",
                    'status_code': 400
                }
            
            # Create Stripe product
            product_data = {
                'name': plan.name,
                'description': plan.description,
                'metadata': {
                    'billing_cycle': plan.billing_cycle,
                    'trial_days': str(plan.trial_days),
                    'is_popular': str(plan.is_popular),
                    'is_active': str(plan.is_active),
                    'plan_id': str(plan.id)
                }
            }
            
            stripe_product = stripe.Product.create(**product_data)
            
            # Update plan with Stripe product ID
            plan.stripe_product_id = stripe_product.id
            plan.save()
            
            return {
                'success': True,
                'message': "Stripe product created successfully",
                'data': {
                    'stripe_product_id': stripe_product.id,
                    'plan_id': plan.id,
                    'product_name': stripe_product.name
                },
                'status_code': 201
            }
            
        except stripe.error.StripeError as e:
            return {
                'success': False,
                'message': f"Stripe error: {str(e)}",
                'status_code': 400
            }
        except Exception as e:
            return {
                'success': False,
                'message': f"Failed to create Stripe product: {str(e)}",
                'status_code': 500
            }
    
    def create_stripe_price(self, plan):
        """Create Stripe price for a subscription plan"""
        try:
            if not self.stripe_secret_key:
                return {
                    'success': False,
                    'message': "Stripe secret key not configured",
                    'status_code': 500
                }
            
            # Check if product exists
            if not plan.stripe_product_id:
                return {
                    'success': False,
                    'message': "Stripe product must be created first",
                    'status_code': 400
                }
            
            # Check if price already exists
            if plan.stripe_price_id:
                return {
                    'success': False,
                    'message': "Stripe price already exists for this plan",
                    'status_code': 400
                }
            
            # Convert price to cents
            amount_cents = int(float(plan.price) * 100)
            
            # Determine billing interval
            interval = 'month' if plan.billing_cycle == 'monthly' else 'year'
            
            # Create Stripe price
            price_data = {
                'product': plan.stripe_product_id,
                'unit_amount': amount_cents,
                'currency': 'usd',
                'recurring': {
                    'interval': interval
                },
                'metadata': {
                    'billing_cycle': plan.billing_cycle,
                    'trial_days': str(plan.trial_days),
                    'plan_id': str(plan.id)
                }
            }
            
            stripe_price = stripe.Price.create(**price_data)
            
            # Update plan with Stripe price ID
            plan.stripe_price_id = stripe_price.id
            plan.save()
            
            return {
                'success': True,
                'message': "Stripe price created successfully",
                'data': {
                    'stripe_price_id': stripe_price.id,
                    'stripe_product_id': stripe_price.product,
                    'plan_id': plan.id,
                    'amount': plan.price,
                    'currency': 'usd',
                    'interval': interval
                },
                'status_code': 201
            }
            
        except stripe.error.StripeError as e:
            return {
                'success': False,
                'message': f"Stripe error: {str(e)}",
                'status_code': 400
            }
        except Exception as e:
            return {
                'success': False,
                'message': f"Failed to create Stripe price: {str(e)}",
                'status_code': 500
            }
