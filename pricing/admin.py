from django.contrib import admin

from .models import PricingRule, PricingRuleAssignment


class AssignmentInline(admin.TabularInline):
    model  = PricingRuleAssignment
    extra  = 1
    fields = ('product', 'category', 'include_subcategories', 'priority')


@admin.register(PricingRule)
class PricingRuleAdmin(admin.ModelAdmin):
    list_display  = ('name', 'method', 'value', 'rounding', 'is_active')
    list_filter   = ('method', 'is_active')
    search_fields = ('name',)
    inlines       = [AssignmentInline]
