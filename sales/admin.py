from django.contrib import admin

from .models import (
    Cart,
    CartLine,
    FulfillmentOrder,
    FulfillmentOrderLine,
    Invoice,
    InvoiceLine,
    InvoicePayment,
    OrderLine,
    Quote,
    QuoteLine,
    SalesOrder,
    Shipment,
    ShipmentLine,
    ShippingOrder,
    ShippingOrderLine,
)


class CartLineInline(admin.TabularInline):
    model = CartLine
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'updated_at')
    inlines = [CartLineInline]


class QuoteLineInline(admin.TabularInline):
    model = QuoteLine
    extra = 0
    readonly_fields = ('line_total',)


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = (
        'reference',
        'relation_organization',
        'status',
        'is_locked',
        'internal_reference',
        'external_reference',
        'created_by',
        'created_at',
    )
    list_filter = ('status', 'is_locked')
    search_fields = ('reference', 'internal_reference', 'external_reference', 'notes')
    autocomplete_fields = ('relation_organization', 'created_by')
    inlines = [QuoteLineInline]


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = ('reference', 'status', 'created_by', 'quote', 'relation_organization', 'created_at')
    list_filter = ('status',)
    search_fields = ('reference',)
    autocomplete_fields = ('quote', 'relation_organization', 'created_by')
    inlines = [OrderLineInline]


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0
    readonly_fields = ('line_total',)


class InvoicePaymentInline(admin.TabularInline):
    model = InvoicePayment
    extra = 0
    readonly_fields = ('created_at',)
    autocomplete_fields = ('created_by',)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        'reference',
        'order',
        'relation_organization',
        'status',
        'currency',
        'created_at',
    )
    list_filter = ('status', 'currency')
    search_fields = ('reference', 'notes')
    autocomplete_fields = ('order', 'relation_organization', 'created_by')
    inlines = [InvoiceLineInline, InvoicePaymentInline]


class FulfillmentOrderLineInline(admin.TabularInline):
    model = FulfillmentOrderLine
    extra = 0


@admin.register(FulfillmentOrder)
class FulfillmentOrderAdmin(admin.ModelAdmin):
    list_display = ('reference', 'sales_order', 'status', 'created_by', 'created_at')
    list_filter = ('status',)
    search_fields = ('reference', 'notes')
    autocomplete_fields = ('sales_order', 'created_by')
    inlines = [FulfillmentOrderLineInline]


class ShippingOrderLineInline(admin.TabularInline):
    model = ShippingOrderLine
    extra = 0
    raw_id_fields = ('fulfillment_line',)


class ShipmentLineInline(admin.TabularInline):
    model = ShipmentLine
    extra = 0
    raw_id_fields = ('shipping_order_line',)


class ShipmentInline(admin.TabularInline):
    model = Shipment
    extra = 0


@admin.register(ShippingOrder)
class ShippingOrderAdmin(admin.ModelAdmin):
    list_display = (
        'reference',
        'sales_order',
        'fulfillment_order',
        'status',
        'created_by',
        'created_at',
    )
    list_filter = ('status',)
    search_fields = ('reference', 'notes')
    autocomplete_fields = ('sales_order', 'fulfillment_order', 'created_by')
    inlines = [ShippingOrderLineInline, ShipmentInline]


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = (
        'shipping_order',
        'sequence',
        'status',
        'carrier',
        'tracking_number',
        'created_at',
    )
    list_filter = ('status',)
    search_fields = ('tracking_number', 'carrier', 'notes')
    autocomplete_fields = ('shipping_order',)
    inlines = [ShipmentLineInline]
