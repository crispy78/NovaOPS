from django.contrib import admin

from .models import StockEntry, StockLocation, StockMovement, Warehouse


class StockLocationInline(admin.TabularInline):
    model = StockLocation
    extra = 1
    fields = ('code', 'name', 'is_active', 'notes')


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'city', 'country', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('code', 'name', 'city')
    inlines = [StockLocationInline]


@admin.register(StockLocation)
class StockLocationAdmin(admin.ModelAdmin):
    list_display = ('warehouse', 'code', 'name', 'is_active')
    list_filter = ('warehouse', 'is_active')
    search_fields = ('code', 'name', 'warehouse__code')


@admin.register(StockEntry)
class StockEntryAdmin(admin.ModelAdmin):
    list_display = ('product', 'location', 'quantity_on_hand', 'last_updated')
    list_filter = ('location__warehouse',)
    search_fields = ('product__sku', 'product__name', 'location__code')
    readonly_fields = ('last_updated',)


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'product', 'location', 'delta', 'movement_type', 'reference', 'created_by')
    list_filter = ('movement_type', 'location__warehouse')
    search_fields = ('product__sku', 'reference')
    readonly_fields = ('created_at',)
