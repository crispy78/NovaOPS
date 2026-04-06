from django.contrib import admin

from .models import (
    Contract,
    ContractTemplate,
    ContractTemplateVariable,
    ContractVariableValue,
    ServiceRate,
)


@admin.register(ServiceRate)
class ServiceRateAdmin(admin.ModelAdmin):
    list_display  = ('name', 'code', 'rate_per_hour', 'currency', 'is_active')
    list_filter   = ('is_active', 'currency')
    search_fields = ('name', 'code')


class ContractTemplateVariableInline(admin.TabularInline):
    model  = ContractTemplateVariable
    extra  = 1
    fields = ('sort_order', 'name', 'label', 'variable_type', 'service_rate', 'constant_value', 'default_value', 'unit')


@admin.register(ContractTemplate)
class ContractTemplateAdmin(admin.ModelAdmin):
    list_display  = ('name', 'result_label', 'is_active')
    list_filter   = ('is_active',)
    search_fields = ('name',)
    inlines       = [ContractTemplateVariableInline]


class ContractVariableValueInline(admin.TabularInline):
    model  = ContractVariableValue
    extra  = 0
    fields = ('variable', 'value')


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display  = ('reference', 'organization', 'template', 'status', 'start_date', 'end_date', 'computed_result')
    list_filter   = ('status',)
    search_fields = ('reference', 'organization__name')
    raw_id_fields = ('quote', 'sales_order', 'asset')
    inlines       = [ContractVariableValueInline]
