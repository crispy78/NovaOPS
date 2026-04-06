from django.contrib import admin

from . import models


@admin.register(models.TaxRate)
class TaxRateAdmin(admin.ModelAdmin):
    readonly_fields = ('id',)
    list_display = ('id', 'name', 'code', 'rate')
    search_fields = ('name', 'code')


@admin.register(models.DiscountGroup)
class DiscountGroupAdmin(admin.ModelAdmin):
    readonly_fields = ('id',)
    list_display = ('id', 'name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name', 'slug')


@admin.register(models.ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    readonly_fields = ('id',)
    list_display = ('id', 'name', 'slug', 'parent')
    list_filter = ('parent',)
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name', 'slug')


class ProductPriceTierInline(admin.TabularInline):
    model = models.ProductPriceTier
    extra = 0


class ProductBOMLineInline(admin.TabularInline):
    model = models.ProductBOMLine
    fk_name = 'bundle_product'
    extra = 0
    autocomplete_fields = ('component_product',)


class ProductRelationInline(admin.TabularInline):
    model = models.ProductRelation
    fk_name = 'from_product'
    extra = 0
    autocomplete_fields = ('to_product',)


class ProductImageInline(admin.TabularInline):
    model = models.ProductImage
    extra = 0


class ProductDocumentInline(admin.TabularInline):
    model = models.ProductDocument
    extra = 0


class ProductITSpecInline(admin.StackedInline):
    model = models.ProductITSpec
    max_num = 1


class ProductConnectivitySpecInline(admin.StackedInline):
    model = models.ProductConnectivitySpec
    max_num = 1


class ProductScannerSpecInline(admin.StackedInline):
    model = models.ProductScannerSpec
    max_num = 1


class ProductPrinterSpecInline(admin.StackedInline):
    model = models.ProductPrinterSpec
    max_num = 1


class ProductDisplaySpecInline(admin.StackedInline):
    model = models.ProductDisplaySpec
    max_num = 1


@admin.register(models.Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'sku', 'name', 'brand', 'category', 'status', 'list_price', 'currency')
    list_filter = ('status', 'category', 'inventory_tracked')
    search_fields = ('sku', 'name', 'ean_gtin', 'mpn', 'brand')
    autocomplete_fields = ('category', 'tax_rate', 'discount_group')
    readonly_fields = ('id',)
    inlines = (
        ProductPriceTierInline,
        ProductBOMLineInline,
        ProductRelationInline,
        ProductImageInline,
        ProductDocumentInline,
        ProductITSpecInline,
        ProductConnectivitySpecInline,
        ProductScannerSpecInline,
        ProductPrinterSpecInline,
        ProductDisplaySpecInline,
    )
    fieldsets = (
        ('System', {
            'fields': ('id',),
        }),
        ('General', {
            'fields': (
                'name', 'short_description', 'long_description', 'brand', 'category', 'status',
            ),
        }),
        ('Identification', {
            'fields': ('sku', 'ean_gtin', 'mpn', 'upc_isbn'),
        }),
        ('Physical', {
            'fields': (
                'length', 'width', 'height', 'dimension_unit',
                'weight_net', 'weight_gross', 'weight_unit',
                'color', 'material', 'size_or_volume',
            ),
        }),
        ('Financial', {
            'fields': (
                'purchase_price', 'list_price', 'msrp', 'currency',
                'tax_rate', 'discount_group',
            ),
        }),
        ('Logistics & stock', {
            'fields': (
                'unit_of_measure', 'minimum_order_quantity',
                'lead_time_days', 'lead_time_text', 'warehouse_location', 'inventory_tracked',
            ),
        }),
        ('Asset & service', {
            'fields': (
                'serial_number_required', 'warranty_months', 'maintenance_interval',
                'depreciation_months', 'asset_type',
            ),
        }),
    )

    def has_delete_permission(self, request, obj=None):
        # Domain data is retained; prefer archive/unarchive instead of hard delete.
        return request.user.is_superuser


@admin.register(models.ProductPriceTier)
class ProductPriceTierAdmin(admin.ModelAdmin):
    list_display = ('product', 'min_quantity', 'max_quantity', 'unit_price')
    list_filter = ('product',)
    autocomplete_fields = ('product',)


@admin.register(models.ProductBOMLine)
class ProductBOMLineAdmin(admin.ModelAdmin):
    readonly_fields = ('id',)
    list_display = ('id', 'bundle_product', 'component_product', 'quantity')
    autocomplete_fields = ('bundle_product', 'component_product')


@admin.register(models.ProductRelation)
class ProductRelationAdmin(admin.ModelAdmin):
    readonly_fields = ('id',)
    list_display = ('id', 'from_product', 'relation_type', 'to_product', 'sort_order')
    list_filter = ('relation_type',)
    autocomplete_fields = ('from_product', 'to_product')


@admin.register(models.ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'is_primary', 'sort_order')
    list_filter = ('is_primary',)
    autocomplete_fields = ('product',)


@admin.register(models.ProductDocument)
class ProductDocumentAdmin(admin.ModelAdmin):
    readonly_fields = ('id',)
    list_display = ('id', 'product', 'document_type', 'title', 'uploaded_at')
    list_filter = ('document_type',)
    autocomplete_fields = ('product',)


@admin.register(models.ProductITSpec)
class ProductITSpecAdmin(admin.ModelAdmin):
    readonly_fields = ('id',)
    list_display = ('id', 'product', 'operating_system', 'cpu')
    autocomplete_fields = ('product',)


@admin.register(models.ProductConnectivitySpec)
class ProductConnectivitySpecAdmin(admin.ModelAdmin):
    list_display = ('product',)
    autocomplete_fields = ('product',)


@admin.register(models.ProductScannerSpec)
class ProductScannerSpecAdmin(admin.ModelAdmin):
    readonly_fields = ('id',)
    list_display = ('id', 'product', 'scan_engine', 'ip_rating')
    autocomplete_fields = ('product',)


@admin.register(models.ProductPrinterSpec)
class ProductPrinterSpecAdmin(admin.ModelAdmin):
    readonly_fields = ('id',)
    list_display = ('id', 'product', 'print_technology', 'print_resolution')
    autocomplete_fields = ('product',)


@admin.register(models.ProductDisplaySpec)
class ProductDisplaySpecAdmin(admin.ModelAdmin):
    readonly_fields = ('id',)
    list_display = ('id', 'product', 'diagonal', 'resolution', 'touchscreen_type')
    autocomplete_fields = ('product',)
