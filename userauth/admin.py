from django.contrib import admin
from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """Simple User admin interface"""
    
    list_display = ['email', 'first_name', 'last_name', 'is_active']
    list_filter = ['is_active', 'registration_method']
    search_fields = ['email', 'first_name', 'last_name']
    ordering = ['-date_joined']
    
    # Make password field read-only
    readonly_fields = ['password']
    
    # Exclude password from the form since it's read-only
    exclude = ['password']
