from django.contrib import admin

from .models import PurchaseOrder, PurchaseOrderLine


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 1
    fields = ('product', 'description', 'qty_ordered', 'unit_cost', 'qty_received')
    readonly_fields = ('qty_received',)


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('ref', 'supplier', 'status', 'expected_delivery_date', 'created_at', 'created_by')
    list_filter = ('status',)
    search_fields = ('ref', 'supplier__name')
    readonly_fields = ('ref', 'created_at', 'created_by')
    inlines = [PurchaseOrderLineInline]


@admin.register(PurchaseOrderLine)
class PurchaseOrderLineAdmin(admin.ModelAdmin):
    list_display = ('purchase_order', 'product', 'qty_ordered', 'qty_received', 'unit_cost')
    search_fields = ('purchase_order__ref', 'product__sku', 'product__name')
    readonly_fields = ('qty_received',)
