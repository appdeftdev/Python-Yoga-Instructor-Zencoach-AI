from django.urls import path, include
from rest_framework.routers import DefaultRouter
from payments import views

app_name = 'payments'

# Create router for ViewSets
router = DefaultRouter()
router.register(r'plans', views.SubscriptionPlanViewSet, basename='subscription-plans')

urlpatterns = [
    # Include router URLs
    path('', include(router.urls)),
    
    # Subscription Management
    path('subscribe/', views.CreateSubscriptionView.as_view(), name='create-subscription'),
    path('current/', views.CurrentSubscriptionView.as_view(), name='current-subscription'),
    path('cancel/', views.CancelSubscriptionView.as_view(), name='cancel-subscription'),
    path('history/', views.SubscriptionHistoryView.as_view(), name='subscription-history'),
    
    # Payment Processing
    path('payment-intent/', views.CreatePaymentIntentView.as_view(), name='create-payment-intent'),
    path('process-subscription-payment/', views.ProcessSubscriptionPaymentView.as_view(), name='process-subscription-payment'),
    
    # Payment Methods Management (Card, Apple Pay, Google Pay)
    path('methods/', views.PaymentMethodView.as_view(), name='payment-methods'),
    path('methods/<int:pk>/', views.PaymentMethodDetailView.as_view(), name='payment-method-detail'),
    
    # Payment History
    path('transactions/', views.PaymentHistoryView.as_view(), name='payment-history'),
    
    # Stripe Product & Price Creation
    path('stripe/create-product/', views.CreateStripeProductView.as_view(), name='create-stripe-product'),
    path('stripe/create-price/', views.CreateStripePriceView.as_view(), name='create-stripe-price'),
    
    # Promo Code Management
    path('promo-codes/', views.CreatePromoCodeView.as_view(), name='create-promo-code'),
    path('apply-promo-code/', views.CalculatePriceView.as_view(), name='apply-promo-code'),
]
