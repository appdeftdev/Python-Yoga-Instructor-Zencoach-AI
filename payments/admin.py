from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils import timezone
from .models import SubscriptionPlan, PromoCode


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    """Enhanced admin interface for SubscriptionPlan with full CRUD functionality"""
    
    # List display configuration
    list_display = [
        'name', 'display_price', 'billing_cycle_display', 'trial_days_display',
        'is_popular_display', 'is_active_display', 'stripe_status', 'created_at'
    ]
    
    # List filters
    list_filter = [
        'billing_cycle', 'is_active', 'is_popular', 'trial_days', 'created_at'
    ]
    
    # Search functionality
    search_fields = [
        'name', 'description', 'stripe_price_id', 'stripe_product_id'
    ]
    
    # Ordering
    ordering = ['price']
    
    # Readonly fields
    readonly_fields = [
        'created_at', 'updated_at', 'display_price', 'trial_info', 
        'monthly_price', 'stripe_status'
    ]
    
    # Fieldsets for organized form layout
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'is_active'),
            'description': 'Basic plan information and status'
        }),
        ('Pricing Details', {
            'fields': ('price', 'original_price', 'billing_cycle', 'display_price', 'monthly_price'),
            'description': 'Plan pricing and billing cycle information'
        }),
        ('Trial & Features', {
            'fields': ('trial_days', 'trial_info', 'features', 'is_popular'),
            'description': 'Trial period and plan features'
        }),
        ('Stripe Integration', {
            'fields': ('stripe_price_id', 'stripe_product_id', 'stripe_status'),
            'classes': ('collapse',),
            'description': 'Stripe product and price IDs for payment processing'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
            'description': 'Record creation and modification timestamps'
        })
    )
    
    # Actions
    actions = ['activate_plans', 'deactivate_plans', 'mark_as_popular', 'unmark_as_popular']
    
    # List per page
    list_per_page = 20
    
    # Custom methods for display
    def display_price(self, obj):
        """Display formatted price"""
        if obj.price:
            return f"${obj.price:.2f}"
        return "-"
    display_price.short_description = "Price"
    display_price.admin_order_field = "price"
    
    def billing_cycle_display(self, obj):
        """Display billing cycle"""
        return obj.get_billing_cycle_display()
    billing_cycle_display.short_description = "Billing Cycle"
    billing_cycle_display.admin_order_field = "billing_cycle"
    
    def trial_days_display(self, obj):
        """Display trial days"""
        if obj.trial_days > 0:
            return f"{obj.trial_days} days"
        return "No trial"
    trial_days_display.short_description = "Trial Period"
    trial_days_display.admin_order_field = "trial_days"
    
    def is_popular_display(self, obj):
        """Display popular status"""
        if obj.is_popular:
            return "Yes"
        return "No"
    is_popular_display.short_description = "Popular"
    is_popular_display.admin_order_field = "is_popular"
    
    def is_active_display(self, obj):
        """Display active status"""
        if obj.is_active:
            return "Active"
        return "Inactive"
    is_active_display.short_description = "Status"
    is_active_display.admin_order_field = "is_active"
    
    def stripe_status(self, obj):
        """Display Stripe integration status"""
        if obj.stripe_price_id and obj.stripe_product_id:
            return "Configured"
        return "Not Configured"
    stripe_status.short_description = "Stripe Status"
    
    def trial_info(self, obj):
        """Display trial information"""
        return obj.get_trial_info()
    trial_info.short_description = "Trial Information"
    
    def monthly_price(self, obj):
        """Display monthly equivalent price"""
        if obj.price:
            if obj.billing_cycle == 'yearly':
                return f"${float(obj.price) / 12:.2f}/month"
            return f"${obj.price}/month"
        return "-"
    monthly_price.short_description = "Monthly Equivalent"
    
    # Custom actions
    def activate_plans(self, request, queryset):
        """Activate selected plans"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} plan(s) were successfully activated.')
    activate_plans.short_description = "Activate selected plans"
    
    def deactivate_plans(self, request, queryset):
        """Deactivate selected plans"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} plan(s) were successfully deactivated.')
    deactivate_plans.short_description = "Deactivate selected plans"
    
    def mark_as_popular(self, request, queryset):
        """Mark selected plans as popular"""
        # First, unmark all other plans as not popular
        SubscriptionPlan.objects.filter(is_popular=True).update(is_popular=False)
        # Then mark selected plans as popular
        updated = queryset.update(is_popular=True)
        self.message_user(request, f'{updated} plan(s) were marked as popular.')
    mark_as_popular.short_description = "Mark as popular (only one can be popular)"
    
    def unmark_as_popular(self, request, queryset):
        """Unmark selected plans as popular"""
        updated = queryset.update(is_popular=False)
        self.message_user(request, f'{updated} plan(s) were unmarked as popular.')
    unmark_as_popular.short_description = "Unmark as popular"
    
    # Form customization
    def get_form(self, request, obj=None, **kwargs):
        """Customize form based on context"""
        form = super().get_form(request, obj, **kwargs)
        
        # Add help text for important fields
        if 'stripe_price_id' in form.base_fields:
            form.base_fields['stripe_price_id'].help_text = "Stripe Price ID (e.g., price_1234567890)"
        if 'stripe_product_id' in form.base_fields:
            form.base_fields['stripe_product_id'].help_text = "Stripe Product ID (e.g., prod_1234567890)"
        if 'features' in form.base_fields:
            form.base_fields['features'].help_text = "List of features (one per line or JSON array)"
            
        return form
    
    # Override save method to ensure only one popular plan
    def save_model(self, request, obj, form, change):
        """Ensure only one plan can be marked as popular"""
        if obj.is_popular:
            # Unmark all other plans as not popular
            SubscriptionPlan.objects.filter(is_popular=True).exclude(id=obj.id).update(is_popular=False)
        super().save_model(request, obj, form, change)
    
    # Custom changelist view
    def changelist_view(self, request, extra_context=None):
        """Add custom context to changelist"""
        extra_context = extra_context or {}
        extra_context['total_plans'] = SubscriptionPlan.objects.count()
        extra_context['active_plans'] = SubscriptionPlan.objects.filter(is_active=True).count()
        extra_context['popular_plan'] = SubscriptionPlan.objects.filter(is_popular=True).first()
        return super().changelist_view(request, extra_context)


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    """Enhanced admin interface for PromoCode with full CRUD functionality"""
    
    # List display configuration
    list_display = [
        'code', 'discount_display', 'validity_display', 'usage_display',
        'is_active_display', 'created_at'
    ]
    
    # List filters
    list_filter = [
        'discount_type', 'is_active', 'valid_from', 'valid_until', 'created_at'
    ]
    
    # Search fields
    search_fields = ['code', 'description']
    
    # Ordering
    ordering = ['-created_at']
    
    # Fields configuration
    fieldsets = (
        ('Basic Information', {
            'fields': ('code', 'description', 'is_active')
        }),
        ('Discount Settings', {
            'fields': ('discount_type', 'discount_value'),
            'description': 'Choose between percentage or fixed amount discount'
        }),
        ('Validity Period', {
            'fields': ('valid_from', 'valid_until'),
            'description': 'Set the time period when this promo code is valid'
        }),
        ('Usage Limits', {
            'fields': ('usage_limit', 'used_count'),
            'description': 'Set maximum usage limit (leave blank for unlimited)'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    # Read-only fields
    readonly_fields = ['used_count', 'created_at', 'updated_at']
    
    # Custom display methods
    def discount_display(self, obj):
        """Display discount in a user-friendly format"""
        if obj.discount_type == 'percentage':
            return f"{obj.discount_value}% off"
        else:
            return f"${obj.discount_value} off"
    discount_display.short_description = "Discount"
    discount_display.admin_order_field = 'discount_value'
    
    def validity_display(self, obj):
        """Display validity period"""
        now = timezone.now()
        
        if obj.valid_from <= now <= obj.valid_until:
            status = "Active"
        elif now < obj.valid_from:
            status = "Future"
        else:
            status = "Expired"
        
        return f"{status} | {obj.valid_from.strftime('%Y-%m-%d')} to {obj.valid_until.strftime('%Y-%m-%d')}"
    validity_display.short_description = "Validity"
    validity_display.admin_order_field = 'valid_from'
    
    def usage_display(self, obj):
        """Display usage statistics"""
        if obj.usage_limit:
            percentage = (obj.used_count / obj.usage_limit) * 100
            return f"{obj.used_count}/{obj.usage_limit} ({percentage:.1f}%)"
        else:
            return f"{obj.used_count}/∞"
    usage_display.short_description = "Usage"
    usage_display.admin_order_field = 'used_count'
    
    def is_active_display(self, obj):
        """Display active status"""
        return "Active" if obj.is_active else "Inactive"
    is_active_display.short_description = "Status"
    is_active_display.admin_order_field = 'is_active'
    
    # Actions
    actions = ['activate_promo_codes', 'deactivate_promo_codes', 'reset_usage_count']
    
    def activate_promo_codes(self, request, queryset):
        """Activate selected promo codes"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} promo code(s) activated successfully.")
    activate_promo_codes.short_description = "Activate selected promo codes"
    
    def deactivate_promo_codes(self, request, queryset):
        """Deactivate selected promo codes"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} promo code(s) deactivated successfully.")
    deactivate_promo_codes.short_description = "Deactivate selected promo codes"
    
    def reset_usage_count(self, request, queryset):
        """Reset usage count for selected promo codes"""
        updated = queryset.update(used_count=0)
        self.message_user(request, f"Usage count reset for {updated} promo code(s).")
    reset_usage_count.short_description = "Reset usage count"
    
    # Custom changelist view
    def changelist_view(self, request, extra_context=None):
        """Add custom context to changelist"""
        extra_context = extra_context or {}
        extra_context['total_codes'] = PromoCode.objects.count()
        extra_context['active_codes'] = PromoCode.objects.filter(is_active=True).count()
        extra_context['expired_codes'] = PromoCode.objects.filter(valid_until__lt=timezone.now()).count()
        return super().changelist_view(request, extra_context)
