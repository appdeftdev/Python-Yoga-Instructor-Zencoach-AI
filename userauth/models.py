from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from datetime import timedelta
import random
import string


class User(AbstractUser):
    
    REGISTRATION_METHODS = [
        ('manual', 'Manual Registration'),
        ('google', 'Google OAuth'),
        ('apple', 'Apple Sign In'),
    ]
    
    registration_method = models.CharField(
        max_length=10, 
        choices=REGISTRATION_METHODS, 
        default='manual',
        help_text='Method used to register this account'
    )
    
    google_id = models.CharField(
        max_length=100, 
        blank=True, 
        null=True, 
        unique=True,
        help_text='Google OAuth unique identifier'
    )
    apple_id = models.CharField(
        max_length=100, 
        blank=True, 
        null=True, 
        unique=True,
        help_text='Apple Sign In unique identifier'
    )
    
    profile_picture = models.URLField(
        blank=True, 
        null=True,
        help_text='URL to user profile picture'
    )
    phone_number = models.CharField(
        max_length=20, 
        blank=True, 
        null=True,
        help_text='User phone number for verification'
    )
    date_of_birth = models.DateField(
        blank=True, 
        null=True,
        help_text='User date of birth'
    )
    is_verified = models.BooleanField(
        default=False,
        help_text='Whether user email/phone is verified'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        indexes = [
            models.Index(fields=['google_id']),
            models.Index(fields=['apple_id']),
            models.Index(fields=['registration_method']),
        ]
    
    def __str__(self):
        return f"{self.username} ({self.get_registration_method_display()})"
    
    @property
    def is_social_user(self):
        """Check if user registered via social login"""
        return self.registration_method in ['google', 'apple']
    
    @property
    def social_id(self):
        """Get the social provider ID based on registration method"""
        if self.registration_method == 'google':
            return self.google_id
        elif self.registration_method == 'apple':
            return self.apple_id
        return None


class EmailVerification(models.Model):
    """Model for email verification codes (password reset)"""
    email = models.EmailField(help_text="Email address for verification")
    verification_code = models.CharField(
        max_length=6, 
        help_text="6-digit verification code"
    )
    is_used = models.BooleanField(
        default=False,
        help_text="Whether this code has been used"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the code was created"
    )
    expires_at = models.DateTimeField(
        help_text="When the code expires"
    )
    
    class Meta:
        db_table = 'email_verification'
        verbose_name = 'Email Verification'
        verbose_name_plural = 'Email Verifications'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['verification_code']),
            models.Index(fields=['expires_at']),
        ]
    
    def __str__(self):
        return f"{self.email} - {self.verification_code}"
    
    @classmethod
    def generate_code(cls, email):
        """Generate a new verification code for email"""
        # Generate 6-digit random code
        code = ''.join(random.choices(string.digits, k=6))
        
        # Set expiry to 15 minutes from now
        expires_at = timezone.now() + timedelta(minutes=15)
        
        # Create verification record
        verification = cls.objects.create(
            email=email,
            verification_code=code,
            expires_at=expires_at
        )
        
        return verification
    
    @property
    def is_expired(self):
        """Check if the verification code has expired"""
        return timezone.now() > self.expires_at
    
    @property
    def is_valid(self):
        """Check if the verification code is valid (not used and not expired)"""
        return not self.is_used and not self.is_expired

