from django.urls import path
from userauth import views

urlpatterns = [
    path('', views.UserProfileView.as_view(), name='user-profile'),
    path('email/', views.update_email, name='update-email'),
]
