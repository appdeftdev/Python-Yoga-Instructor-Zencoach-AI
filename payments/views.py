from rest_framework import status
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from decimal import Decimal
import json

from .models import SubscriptionPlan, UserSubscription, PaymentMethod, PaymentTransaction, PromoCode
from .serializers import (
    SubscriptionPlanSerializer, UserSubscriptionSerializer, PaymentMethodSerializer,
    PaymentTransactionSerializer, CreateSubscriptionSerializer, CancelSubscriptionSerializer,
    CreatePaymentIntentSerializer, CreatePaymentMethodSerializer
)
from .services import SubscriptionService, PaymentService, WebhookService, StripeProductService, StripeService
from utils.response_format import success_response, error_response, validation_error_response


class SubscriptionPlanViewSet(ModelViewSet):
    """ViewSet for subscription plans - handles GET (list) and POST (create)"""
    
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [AllowAny]  # Public access for viewing plans
    
    def get_queryset(self):
        """Filter active plans for list view"""
        return SubscriptionPlan.objects.filter(is_active=True).order_by('price')
    
    def list(self, request, *args, **kwargs):
        """Get all subscription plans"""
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            
            return success_response(
                "Subscription plans retrieved successfully",
                data={'plans': serializer.data}
            )
        except Exception as e:
            return error_response(f"Failed to get plans: {str(e)}", 
                                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def create(self, request, *args, **kwargs):
        """Create a new subscription plan"""
        try:
            serializer = self.get_serializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return success_response(
                    "Subscription plan created successfully",
                    data={'plan': serializer.data},
                    status_code=status.HTTP_201_CREATED
                )
            else:
                return error_response(
                    "Invalid data", 
                    errors=serializer.errors,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            return error_response(f"Failed to create plan: {str(e)}", 
                                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def retrieve(self, request, *args, **kwargs):
        """Get specific subscription plan"""
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return success_response(
                "Subscription plan retrieved successfully",
                data={'plan': serializer.data}
            )
        except Exception as e:
            return error_response(f"Failed to get plan: {str(e)}", 
                                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def update(self, request, *args, **kwargs):
        """Update subscription plan"""
        try:
            partial = kwargs.pop('partial', False)
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            if serializer.is_valid():
                serializer.save()
                return success_response(
                    "Subscription plan updated successfully",
                    data={'plan': serializer.data}
                )
            else:
                return error_response(
                    "Invalid data",
                    errors=serializer.errors,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            return error_response(f"Failed to update plan: {str(e)}", 
                                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def destroy(self, request, *args, **kwargs):
        """Delete subscription plan"""
        try:
            instance = self.get_object()
            instance.delete()
            return success_response("Subscription plan deleted successfully")
        except Exception as e:
            return error_response(f"Failed to delete plan: {str(e)}", 
                                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CreateSubscriptionView(APIView):
    """Create a new subscription for user"""
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            plan_id = request.data.get('plan_id')
            if not plan_id:
                return Response(error_response("plan_id is required"), 
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Check if user already has a subscription
            if UserSubscription.objects.filter(user=request.user).exists():
                return Response(error_response("User already has an active subscription"), 
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Get the subscription plan
            try:
                plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
            except SubscriptionPlan.DoesNotExist:
                return Response(error_response("Invalid or inactive plan"), 
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Calculate billing periods
            from django.utils import timezone
            from datetime import timedelta
            
            now = timezone.now()
            if plan.billing_cycle == 'monthly':
                period_end = now + timedelta(days=30)
            else:  # yearly
                period_end = now + timedelta(days=365)
            
            # Create UserSubscription
            subscription = UserSubscription.objects.create(
                user=request.user,
                plan=plan,
                status='pending',  # Will be updated to 'active' after payment
                current_period_start=now,
                current_period_end=period_end,
                trial_start=now if plan.trial_days > 0 else None,
                trial_end=now + timedelta(days=plan.trial_days) if plan.trial_days > 0 else None
            )
            
            # Serialize the response
            serializer = UserSubscriptionSerializer(subscription)
            return success_response(
                "Subscription created successfully",
                data={'subscription': serializer.data},
                status_code=status.HTTP_201_CREATED
            )
            
        except Exception as e:
            return error_response(f"Failed to create subscription: {str(e)}", 
                                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CurrentSubscriptionView(APIView):
    """Get user's current subscription"""
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            # Get user's subscription
            try:
                subscription = UserSubscription.objects.get(user=request.user)
            except UserSubscription.DoesNotExist:
                return error_response("No subscription found", 
                                    status_code=status.HTTP_404_NOT_FOUND)
            
            # Serialize the response
            serializer = UserSubscriptionSerializer(subscription)
            return success_response(
                "Subscription retrieved successfully",
                data={'subscription': serializer.data}
            )
            
        except Exception as e:
            return error_response(f"Failed to get subscription: {str(e)}", 
                                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CancelSubscriptionView(APIView):
    """Cancel user's subscription"""
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = CancelSubscriptionSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_error_response(
                message="Invalid request data",
                errors=serializer.errors
            )
        
        try:
            service = SubscriptionService()
            result = service.cancel_subscription(
                user=request.user,
                cancel_immediately=serializer.validated_data.get('cancel_immediately', False),
                reason=serializer.validated_data.get('reason')
            )
            
            # The service returns a Response object, so we return it directly
            return result
            
        except Exception as e:
            return error_response(
                message="An unexpected error occurred",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CreatePaymentIntentView(APIView):
    """Create payment intent for processing payment"""
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            amount = request.data.get('amount')
            currency = request.data.get('currency', 'USD')
            payment_method_id = request.data.get('payment_method_id')
            
            if not amount:
                return error_response("Amount is required", status_code=400)
            
            try:
                amount = float(amount)
            except (ValueError, TypeError):
                return error_response("Invalid amount format", status_code=400)
            
            service = PaymentService()
            return service.create_payment_intent(
                user=request.user,
                amount=amount,
                currency=currency,
                payment_method_id=payment_method_id
            )
            
        except Exception as e:
            return error_response(f"Failed to create payment intent: {str(e)}", 
                                status_code=500)


class ProcessSubscriptionPaymentView(APIView):
    """Process payment for a subscription"""
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            subscription_id = request.data.get('subscription_id')
            payment_method_id = request.data.get('payment_method_id')
            promo_code = request.data.get('promo_code')
            
            if not subscription_id:
                return error_response("Subscription ID is required", status_code=400)
            
            service = PaymentService()
            return service.process_subscription_payment(
                user=request.user,
                subscription_id=subscription_id,
                payment_method_id=payment_method_id,
                promo_code=promo_code
            )
            
        except Exception as e:
            return error_response(f"Failed to process subscription payment: {str(e)}", 
                                status_code=500)




class PaymentMethodView(APIView):
    """Save payment methods only - no processing (Card, Apple Pay, Google Pay)"""
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """Save any payment method type"""
        try:
            serializer = CreatePaymentMethodSerializer(data=request.data)
            if not serializer.is_valid():
                return error_response("Invalid data", serializer.errors, status_code=400)
            
            validated_data = serializer.validated_data
            payment_type = validated_data['payment_type']
            
            service = PaymentService()
            return service.save_payment_method(
                user=request.user,
                payment_type=payment_type,
                data=validated_data
            )
            
        except Exception as e:
            return error_response(f"Failed to save payment method: {str(e)}", status_code=500)
    
    def get(self, request):
        """Get user's saved payment methods"""
        try:
            service = PaymentService()
            return service.get_saved_payment_methods(request.user)
        except Exception as e:
            return error_response(f"Failed to get payment methods: {str(e)}", status_code=500)


class PaymentMethodDetailView(APIView):
    """Get or update specific payment method (no deletion allowed)"""
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        """Get specific payment method details"""
        try:
            payment_method = get_object_or_404(PaymentMethod, pk=pk, user=request.user)
            serializer = PaymentMethodSerializer(payment_method)
            return success_response(
                "Payment method retrieved successfully",
                data={'payment_method': serializer.data}
            )
        except Exception as e:
            return error_response(f"Failed to get payment method: {str(e)}", 
                                status_code=500)
    
    def put(self, request, pk):
        """Set payment method as default (only operation allowed)"""
        try:
            payment_method = get_object_or_404(PaymentMethod, pk=pk, user=request.user)
            
            # Only allow setting as default
            if 'is_default' in request.data and request.data['is_default']:
                # Unset all other default methods
                PaymentMethod.objects.filter(
                    user=request.user, 
                    is_default=True
                ).update(is_default=False)
                
                # Set this one as default
                payment_method.is_default = True
                payment_method.save()
                
                return success_response("Default payment method updated successfully")
            else:
                return error_response("Only setting default status is allowed", status_code=400)
                
        except Exception as e:
            return error_response(f"Failed to update payment method: {str(e)}", status_code=500)
    
    def delete(self, request, pk):
        """Delete payment method - NOT ALLOWED"""
        return error_response("Payment methods cannot be deleted", status_code=405)


class PaymentHistoryView(APIView):
    """Get user's payment history"""
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        service = PaymentService()
        result = service.get_payment_history(request.user)
        
        if result['success']:
            transactions = result['data']['transactions']
            serializer = PaymentTransactionSerializer(transactions, many=True)
            return success_response(
                "Payment history retrieved successfully",
                data={'transactions': serializer.data}
            )
        else:
            return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhookView(APIView):
    """Handle Stripe webhook events"""
    
    permission_classes = []
    
    def post(self, request):
        try:
            # Get the raw request body
            payload = request.body
            sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
            
            service = WebhookService()
            result = service.handle_stripe_webhook(payload, sig_header)
            
            # Check if result is already a Response object
            if hasattr(result, 'data'):
                return result
            
            # If result is a dictionary, return it as JSON
            if result.get('success'):
                return Response(result, status=status.HTTP_200_OK)
            else:
                return Response(result, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            return Response(error_response(f"Webhook error: {str(e)}"), 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SubscriptionHistoryView(APIView):
    """Get user's subscription history"""
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            subscription = get_object_or_404(UserSubscription, user=request.user)
            history = subscription.history.all().order_by('-created_at')
            
            from .serializers import SubscriptionHistorySerializer
            serializer = SubscriptionHistorySerializer(history, many=True)
            
            return success_response(
                "Subscription history retrieved successfully",
                data={'history': serializer.data}
            )
        except Exception as e:
            return Response(error_response(f"Failed to get subscription history: {str(e)}"), 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CreateStripeProductView(APIView):
    """Create Stripe products for subscription plans"""
    
    permission_classes = [AllowAny]  # Allow without authentication for admin operations
    
    def post(self, request):
        """Create Stripe product for a subscription plan"""
        try:
            plan_id = request.data.get('plan_id')
            if not plan_id:
                return Response(error_response("plan_id is required"), 
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Get the subscription plan
            try:
                plan = SubscriptionPlan.objects.get(id=plan_id)
            except SubscriptionPlan.DoesNotExist:
                return Response(error_response("Invalid plan ID"), 
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Create Stripe product
            service = StripeProductService()
            result = service.create_stripe_product(plan)
            
            if result['success']:
                return Response(result, status=status.HTTP_201_CREATED)
            else:
                return Response(result, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            return Response(error_response(f"Failed to create Stripe product: {str(e)}"), 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CreateStripePriceView(APIView):
    """Create Stripe prices for subscription plans"""
    
    permission_classes = [AllowAny]  # Allow without authentication for admin operations
    
    def post(self, request):
        """Create Stripe price for a subscription plan"""
        try:
            plan_id = request.data.get('plan_id')
            if not plan_id:
                return Response(error_response("plan_id is required"), 
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Get the subscription plan
            try:
                plan = SubscriptionPlan.objects.get(id=plan_id)
            except SubscriptionPlan.DoesNotExist:
                return Response(error_response("Invalid plan ID"), 
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Create Stripe price
            service = StripeProductService()
            result = service.create_stripe_price(plan)
            
            if result['success']:
                return Response(result, status=status.HTTP_201_CREATED)
            else:
                return Response(result, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            return Response(error_response(f"Failed to create Stripe price: {str(e)}"), 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CreatePromoCodeView(APIView):
    """Create a new promo code"""
    
    permission_classes = [IsAuthenticated]  # Only authenticated users can create promo codes
    
    def post(self, request):
        try:
            code = request.data.get('code')
            discount_type = request.data.get('discount_type')
            discount_value = request.data.get('discount_value')
            valid_from = request.data.get('valid_from')
            valid_until = request.data.get('valid_until')
            usage_limit = request.data.get('usage_limit')
            description = request.data.get('description', '')
            
            # Validate required fields
            if not all([code, discount_type, discount_value, valid_from, valid_until]):
                return error_response("Missing required fields: code, discount_type, discount_value, valid_from, valid_until", 
                                    status_code=400)
            
            # Validate discount type
            if discount_type not in ['percentage', 'fixed']:
                return error_response("Invalid discount_type. Must be 'percentage' or 'fixed'", 
                                    status_code=400)
            
            # Validate discount value
            try:
                discount_value = float(discount_value)
                if discount_value <= 0:
                    return error_response("Discount value must be greater than 0", status_code=400)
            except (ValueError, TypeError):
                return error_response("Invalid discount_value format", status_code=400)
            
            # Check if code already exists
            if PromoCode.objects.filter(code=code).exists():
                return error_response("Promo code already exists", status_code=400)
            
            # Create promo code
            promo_code = PromoCode.objects.create(
                code=code,
                discount_type=discount_type,
                discount_value=discount_value,
                valid_from=valid_from,
                valid_until=valid_until,
                usage_limit=usage_limit,
                description=description
            )
            
            return success_response(
                "Promo code created successfully",
                data={
                    'id': promo_code.id,
                    'code': promo_code.code,
                    'discount_type': promo_code.discount_type,
                    'discount_value': promo_code.discount_value,
                    'valid_from': promo_code.valid_from,
                    'valid_until': promo_code.valid_until,
                    'usage_limit': promo_code.usage_limit,
                    'description': promo_code.description,
                    'is_active': promo_code.is_active
                },
                status_code=201
            )
            
        except Exception as e:
            return error_response(f"Failed to create promo code: {str(e)}", 
                                status_code=500)


class CalculatePriceView(APIView):
    """Calculate price with promo code discount"""
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            plan_id = request.data.get('plan_id')
            promo_code = request.data.get('promo_code')
            
            if not plan_id:
                return error_response("plan_id is required", status_code=400)
            
            # Get the subscription plan
            try:
                plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
            except SubscriptionPlan.DoesNotExist:
                return error_response("Invalid or inactive plan", status_code=400)
            
            # Initialize response data
            response_data = {
                'plan': {
                    'id': plan.id,
                    'name': plan.name,
                    'original_price': float(plan.price),
                    'billing_cycle': plan.billing_cycle
                },
                'promo_code': None,
                'pricing': {
                    'original_amount': float(plan.price),
                    'discount_applied': 0.0,
                    'final_amount': float(plan.price),
                    'savings': 0.0
                }
            }
            
            # If promo code provided, validate and calculate discount
            if promo_code:
                try:
                    promo = PromoCode.objects.get(code=promo_code)
                    
                    # Check if promo code is valid
                    if not promo.is_valid():
                        return error_response("Promo code is expired or inactive", status_code=400)
                    
                    # Check if user already used this code
                    if not promo.can_be_used_by_user(request.user):
                        return error_response("You have already used this promo code", status_code=400)
                    
                    # Calculate discount
                    plan_price = Decimal(str(plan.price))
                    promo_value = Decimal(str(promo.discount_value))
                    
                    if promo.discount_type == 'percentage':
                        discount_amount = plan_price * (promo_value / 100)
                    else:  # fixed amount
                        discount_amount = promo_value
                    
                    # Ensure discount doesn't exceed original price
                    discount_amount = min(discount_amount, plan_price)
                    
                    final_amount = plan_price - discount_amount
                    
                    # Update response data
                    response_data['promo_code'] = {
                        'code': promo.code,
                        'discount_type': promo.discount_type,
                        'discount_value': float(promo.discount_value),
                        'description': promo.description
                    }
                    
                    response_data['pricing'] = {
                        'original_amount': float(plan.price),
                        'discount_applied': float(discount_amount),
                        'final_amount': float(final_amount),
                        'savings': float(discount_amount)
                    }
                    
                except PromoCode.DoesNotExist:
                    return error_response("Invalid promo code", status_code=400)
            
            return success_response(
                "Price calculated successfully",
                data=response_data
            )
            
        except Exception as e:
            return error_response(f"Failed to calculate price: {str(e)}", 
                                status_code=500)