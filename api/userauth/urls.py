from django.urls import path
from userauth import views

urlpatterns = [
    # Manual authentication
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    
    # Social authentication
    path('google/', views.google_auth_view, name='google_auth'),
    path('apple/', views.apple_auth_view, name='apple_auth'),
    
    # Token management
    path('refresh/', views.refresh_token_view, name='refresh_token'),
    
    # Password reset
    path('forgot-password/', views.forgot_password_view, name='forgot_password'),
    path('reset-password/', views.reset_password_view, name='reset_password'),
    
    # Test page
    path('apple-test/', views.apple_test_view, name='apple_test'),
    
    # Apple callback
    path('apple/callback/', views.apple_callback_view, name='apple_callback'),
    
    # User data management
    path('delete-user-data/', views.delete_user_data, name='delete_user_data'),
    
    # User listing
    path('users/', views.list_all_users, name='list_all_users'),
]
