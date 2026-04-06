from decimal import Decimal
import os

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import UUIDPrimaryKeyModel

MONEY = dict(max_digits=12, decimal_places=2)
DIM = dict(max_digits=12, decimal_places=4)
WEIGHT = dict(max_digits=12, decimal_places=4)
BOM_QTY = dict(max_digits=10, decimal_places=3)


class TaxRate(UUIDPrimaryKeyModel):
    """VAT or sales tax rate for quoting and invoicing."""

    name = models.CharField(max_length=100, verbose_name='name')
    code = models.CharField(
        max_length=32,
        blank=True,
        db_index=True,
        verbose_name='tax code',
        help_text='Short code for integrations (e.g. NL_HIGH).',
    )
    rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name='rate (%)',
        help_text='Percentage, e.g. 21.00 for 21%.',
    )

    class Meta:
        verbose_name = 'tax rate'
        verbose_name_plural = 'tax rates'
        ordering = ['name']

    def __str__(self) -> str:
        return f'{self.name} ({self.rate}%)'


class DiscountGroup(UUIDPrimaryKeyModel):
    """Default discount group for customer segments (stub for future pricing rules)."""

    name = models.CharField(max_length=100, verbose_name='name')
    slug = models.SlugField(unique=True, verbose_name='slug')

    class Meta:
        verbose_name = 'discount group'
        verbose_name_plural = 'discount groups'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class ProductCategory(UUIDPrimaryKeyModel):
    """Hierarchical category for filters and price lists (e.g. Hardware > Laptops > Business)."""

    name = models.CharField(max_length=200, verbose_name='name')
    slug = models.SlugField(unique=True, verbose_name='slug')
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='children',
        verbose_name='parent category',
    )

    class Meta:
        verbose_name = 'product category'
        verbose_name_plural = 'product categories'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class ProductStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    ACTIVE = 'active', 'Active'
    END_OF_LIFE = 'end_of_life', 'End of life'
    UNAVAILABLE = 'unavailable', 'Unavailable'


class AssetType(models.TextChoices):
    LOAN = 'loan', 'Loan device'
    SOLD = 'sold', 'Sold device'
    INTERNAL = 'internal', 'Internal asset'


class Product(UUIDPrimaryKeyModel):
    """Product master record: identification, physical, financial defaults, logistics, and asset defaults."""

    # --- General ---
    name = models.CharField(max_length=255, verbose_name='product name')
    short_description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='short description',
        help_text='For quotes and order lines (max 255 characters).',
    )
    long_description = models.TextField(blank=True, verbose_name='long description')
    brand = models.CharField(max_length=120, blank=True, verbose_name='brand / manufacturer')
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.PROTECT,
        related_name='products',
        verbose_name='category',
    )
    status = models.CharField(
        max_length=20,
        choices=ProductStatus,
        default=ProductStatus.DRAFT,
        db_index=True,
        verbose_name='product status',
    )

    # --- Lifecycle / retention ---
    is_archived = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name='archived',
        help_text='Archived products are hidden from most users but retained for audit/history.',
    )
    archived_at = models.DateTimeField(null=True, blank=True, verbose_name='archived at')

    # --- Identification (business keys; not primary keys) ---
    sku = models.CharField(max_length=64, unique=True, db_index=True, verbose_name='SKU')
    ean_gtin = models.CharField(
        max_length=32,
        blank=True,
        db_index=True,
        verbose_name='EAN / GTIN',
    )
    mpn = models.CharField(max_length=120, blank=True, verbose_name='MPN (manufacturer part number)')
    upc_isbn = models.CharField(max_length=32, blank=True, verbose_name='UPC / ISBN')

    # --- Physical ---
    length = models.DecimalField(**DIM, null=True, blank=True, verbose_name='length')
    width = models.DecimalField(**DIM, null=True, blank=True, verbose_name='width')
    height = models.DecimalField(**DIM, null=True, blank=True, verbose_name='height')
    dimension_unit = models.CharField(
        max_length=10,
        blank=True,
        verbose_name='dimension unit',
        help_text='e.g. mm, cm',
    )
    weight_net = models.DecimalField(**WEIGHT, null=True, blank=True, verbose_name='net weight')
    weight_gross = models.DecimalField(**WEIGHT, null=True, blank=True, verbose_name='gross weight')
    weight_unit = models.CharField(
        max_length=10,
        blank=True,
        verbose_name='weight unit',
        help_text='e.g. g, kg',
    )
    color = models.CharField(max_length=120, blank=True, verbose_name='color')
    material = models.CharField(max_length=120, blank=True, verbose_name='material')
    size_or_volume = models.CharField(
        max_length=120,
        blank=True,
        verbose_name='size / volume',
        help_text='e.g. clothing size or volume in liters.',
    )

    # --- Financial (defaults) ---
    purchase_price = models.DecimalField(**MONEY, null=True, blank=True, verbose_name='purchase price (cost)')
    list_price = models.DecimalField(**MONEY, null=True, blank=True, verbose_name='standard list price')
    msrp = models.DecimalField(
        **MONEY,
        null=True,
        blank=True,
        verbose_name='MSRP',
        help_text='Manufacturer suggested retail price.',
    )
    currency = models.CharField(
        max_length=3,
        default='EUR',
        verbose_name='currency',
        help_text='ISO 4217 code (e.g. EUR).',
    )
    tax_rate = models.ForeignKey(
        TaxRate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='products',
        verbose_name='tax rate',
    )
    discount_group = models.ForeignKey(
        DiscountGroup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='products',
        verbose_name='discount group',
    )

    # --- Logistics / stock ---
    unit_of_measure = models.CharField(
        max_length=32,
        blank=True,
        verbose_name='unit of measure',
        help_text='e.g. piece, box (12), pallet.',
    )
    minimum_order_quantity = models.PositiveIntegerField(default=1, verbose_name='minimum order quantity (MOQ)')
    lead_time_days = models.PositiveIntegerField(null=True, blank=True, verbose_name='lead time (days)')
    lead_time_text = models.CharField(
        max_length=120,
        blank=True,
        verbose_name='lead time (text)',
        help_text='e.g. "2–3 business days" when not expressed as a single number of days.',
    )
    warehouse_location = models.CharField(max_length=120, blank=True, verbose_name='warehouse location')
    inventory_tracked = models.BooleanField(default=True, verbose_name='inventory tracked')

    # --- Asset / service (catalog defaults) ---
    serial_number_required = models.BooleanField(default=False, verbose_name='serial number required')
    warranty_months = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='warranty (months)')
    maintenance_interval = models.CharField(
        max_length=120,
        blank=True,
        verbose_name='maintenance interval',
        help_text='e.g. "Every 12 months".',
    )
    depreciation_months = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='depreciation (months)')
    asset_type = models.CharField(
        max_length=20,
        choices=AssetType,
        blank=True,
        null=True,
        verbose_name='asset type',
        help_text='Used when this product becomes an installed asset.',
    )

    class Meta:
        verbose_name = 'product'
        verbose_name_plural = 'products'
        ordering = ['name']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['category']),
        ]
        permissions = [
            (
                'view_product_purchase_price',
                'Can view purchase price on the catalog frontend',
            ),
            (
                'edit_product_pricing',
                'Can edit list price, MSRP, currency, tax, and discount fields',
            ),
            (
                'archive_product',
                'Can archive/unarchive products (soft delete)',
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse('catalog:product_detail', kwargs={'pk': self.pk})

    def get_edit_url(self) -> str:
        from django.urls import reverse

        return reverse('catalog:product_edit', kwargs={'pk': self.pk})


def _tier_upper_bound(max_quantity: int | None) -> Decimal:
    if max_quantity is None:
        return Decimal('999999999999')  # practical infinity for overlap checks
    return Decimal(max_quantity)


class ProductPriceTier(UUIDPrimaryKeyModel):
    """Quantity break pricing for a product (currency matches product)."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='price_tiers',
        verbose_name='product',
    )
    min_quantity = models.PositiveIntegerField(verbose_name='minimum quantity')
    max_quantity = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='maximum quantity',
        help_text='Leave empty for an open-ended tier (e.g. 50+).',
    )
    unit_price = models.DecimalField(**MONEY, verbose_name='unit price')

    class Meta:
        verbose_name = 'product price tier'
        verbose_name_plural = 'product price tiers'
        ordering = ['product', 'min_quantity']

    def __str__(self) -> str:
        rng = f'{self.min_quantity}–{self.max_quantity}' if self.max_quantity else f'{self.min_quantity}+'
        return f'{self.product.sku}: {rng} @ {self.unit_price}'

    def clean(self) -> None:
        super().clean()
        if self.max_quantity is not None and self.max_quantity < self.min_quantity:
            raise ValidationError({'max_quantity': 'Maximum quantity must be greater than or equal to minimum quantity.'})

        if self.product_id:
            others = ProductPriceTier.objects.filter(product_id=self.product_id).exclude(pk=self.pk)
            lo = Decimal(self.min_quantity)
            hi = _tier_upper_bound(self.max_quantity)
            for other in others:
                o_lo = Decimal(other.min_quantity)
                o_hi = _tier_upper_bound(other.max_quantity)
                if lo <= o_hi and o_lo <= hi:
                    raise ValidationError(
                        'This tier overlaps another quantity range for the same product.',
                    )

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)


class ProductBOMLine(UUIDPrimaryKeyModel):
    """Bill of materials: bundle product consists of component products."""

    bundle_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='bundle_components',
        verbose_name='bundle product',
    )
    component_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='component_of_bundles',
        verbose_name='component product',
    )
    quantity = models.DecimalField(**BOM_QTY, default=Decimal('1'), verbose_name='quantity')

    class Meta:
        verbose_name = 'BOM line'
        verbose_name_plural = 'BOM lines'
        constraints = [
            models.UniqueConstraint(
                fields=['bundle_product', 'component_product'],
                name='catalog_bom_unique_bundle_component',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.bundle_product.sku} ← {self.quantity}× {self.component_product.sku}'

    def clean(self) -> None:
        super().clean()
        if self.bundle_product_id and self.component_product_id and self.bundle_product_id == self.component_product_id:
            raise ValidationError('A bundle cannot list itself as a component.')

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)


class ProductRelationType(models.TextChoices):
    ACCESSORY = 'accessory', 'Accessory'
    ALTERNATIVE = 'alternative', 'Alternative'
    UPSELL = 'upsell', 'Upsell'
    REPLACEMENT = 'replacement', 'Replacement (EOL / discontinued)'


class ProductRelation(UUIDPrimaryKeyModel):
    """Cross-sell links: accessories, stock alternatives, upsells."""

    from_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='relations_from',
        verbose_name='from product',
    )
    to_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='relations_to',
        verbose_name='to product',
    )
    relation_type = models.CharField(
        max_length=20,
        choices=ProductRelationType,
        verbose_name='relation type',
    )
    sort_order = models.PositiveSmallIntegerField(default=0, verbose_name='sort order')

    class Meta:
        verbose_name = 'product relation'
        verbose_name_plural = 'product relations'
        ordering = ['from_product', 'relation_type', 'sort_order', 'to_product']
        constraints = [
            models.UniqueConstraint(
                fields=['from_product', 'to_product', 'relation_type'],
                name='catalog_relation_unique_triple',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.from_product.sku} —{self.relation_type}→ {self.to_product.sku}'

    def clean(self) -> None:
        super().clean()
        if self.from_product_id and self.to_product_id and self.from_product_id == self.to_product_id:
            raise ValidationError('From and to product must be different.')

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)


def product_image_upload_to(instance: 'ProductImage', filename: str) -> str:
    _, ext = os.path.splitext(filename or '')
    ext = (ext or '').lower()
    if not ext or len(ext) > 10:
        ext = '.bin'
    product_id = str(instance.product_id) if instance.product_id else 'unassigned'
    return f'catalog/product-images/{product_id}/{instance.id}{ext}'


class ProductImage(UUIDPrimaryKeyModel):
    """Primary and gallery images for a product."""

    product = models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='images',
        verbose_name='product',
    )
    image = models.ImageField(upload_to=product_image_upload_to, verbose_name='image')
    original_filename = models.CharField(max_length=255, blank=True, verbose_name='original filename')
    file_size = models.BigIntegerField(null=True, blank=True, verbose_name='file size (bytes)')
    uploaded_at = models.DateTimeField(default=timezone.now, db_index=True, verbose_name='uploaded at')
    is_primary = models.BooleanField(default=False, verbose_name='primary image')
    sort_order = models.PositiveSmallIntegerField(default=0, verbose_name='sort order')
    alt_text = models.CharField(max_length=255, blank=True, verbose_name='alternative text')

    class Meta:
        verbose_name = 'product image'
        verbose_name_plural = 'product images'
        ordering = ['-uploaded_at', 'pk']

    def __str__(self) -> str:
        if self.product_id:
            return f'{self.product.sku} image #{self.pk}'
        return f'Unassigned image #{self.pk}'

    def save(self, *args, **kwargs) -> None:
        if self.image and not self.original_filename:
            self.original_filename = os.path.basename(getattr(self.image, 'name', '') or '')
        try:
            if self.image and self.file_size is None:
                self.file_size = int(self.image.size)
        except Exception:
            pass
        super().save(*args, **kwargs)


class ProductDocumentType(models.TextChoices):
    DATASHEET = 'datasheet', 'Datasheet / specifications'
    MANUAL = 'manual', 'User manual'
    CERTIFICATION = 'certification', 'Certification'
    MSDS = 'msds', 'MSDS / safety sheet'
    OTHER = 'other', 'Other'


class ProductDocument(UUIDPrimaryKeyModel):
    """Datasheets, manuals, certifications, MSDS."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='documents',
        verbose_name='product',
    )
    document_type = models.CharField(
        max_length=20,
        choices=ProductDocumentType,
        default=ProductDocumentType.OTHER,
        verbose_name='document type',
    )
    title = models.CharField(max_length=255, blank=True, verbose_name='title')
    file = models.FileField(upload_to='catalog/documents/%Y/%m/', verbose_name='file')
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name='uploaded at')

    class Meta:
        verbose_name = 'product document'
        verbose_name_plural = 'product documents'
        ordering = ['-uploaded_at']

    def __str__(self) -> str:
        return self.title or f'{self.product.sku} ({self.get_document_type_display()})'


class ProductITSpec(UUIDPrimaryKeyModel):
    """IT / computing specifications (OS, CPU, RAM, storage)."""

    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name='it_spec',
        verbose_name='product',
    )
    operating_system = models.CharField(max_length=200, blank=True, verbose_name='operating system')
    cpu = models.CharField(max_length=200, blank=True, verbose_name='processor (CPU)')
    ram = models.CharField(max_length=120, blank=True, verbose_name='RAM')
    storage = models.CharField(max_length=120, blank=True, verbose_name='storage')

    class Meta:
        verbose_name = 'product IT specification'
        verbose_name_plural = 'product IT specifications'

    def __str__(self) -> str:
        return f'IT spec: {self.product.sku}'


class ProductConnectivitySpec(UUIDPrimaryKeyModel):
    """Physical ports and wireless connectivity (free text for v1)."""

    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name='connectivity_spec',
        verbose_name='product',
    )
    io_ports = models.TextField(blank=True, verbose_name='I/O ports')
    wireless = models.TextField(blank=True, verbose_name='wireless connectivity')

    class Meta:
        verbose_name = 'product connectivity specification'
        verbose_name_plural = 'product connectivity specifications'

    def __str__(self) -> str:
        return f'Connectivity: {self.product.sku}'


class ProductScannerSpec(UUIDPrimaryKeyModel):
    """Scanner / handheld terminal attributes."""

    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name='scanner_spec',
        verbose_name='product',
    )
    scan_engine = models.CharField(max_length=200, blank=True, verbose_name='scan engine')
    drop_spec = models.CharField(max_length=200, blank=True, verbose_name='drop specification')
    ip_rating = models.CharField(max_length=40, blank=True, verbose_name='IP rating')
    battery_mah = models.PositiveIntegerField(null=True, blank=True, verbose_name='battery (mAh)')
    battery_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='battery life (hours)',
    )

    class Meta:
        verbose_name = 'product scanner specification'
        verbose_name_plural = 'product scanner specifications'

    def __str__(self) -> str:
        return f'Scanner: {self.product.sku}'


class ProductPrinterSpec(UUIDPrimaryKeyModel):
    """Thermal / receipt printer attributes."""

    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name='printer_spec',
        verbose_name='product',
    )
    print_technology = models.CharField(max_length=120, blank=True, verbose_name='print technology')
    print_resolution = models.CharField(max_length=80, blank=True, verbose_name='print resolution')
    print_width = models.CharField(max_length=80, blank=True, verbose_name='print width / media format')
    cutter_type = models.CharField(max_length=120, blank=True, verbose_name='cutter / tear bar')

    class Meta:
        verbose_name = 'product printer specification'
        verbose_name_plural = 'product printer specifications'

    def __str__(self) -> str:
        return f'Printer: {self.product.sku}'


class TouchscreenType(models.TextChoices):
    NONE = 'none', 'None'
    CAPACITIVE = 'capacitive', 'Capacitive (PCAP)'
    RESISTIVE = 'resistive', 'Resistive'


class ProductDisplaySpec(UUIDPrimaryKeyModel):
    """Customer display / monitor attributes."""

    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name='display_spec',
        verbose_name='product',
    )
    diagonal = models.CharField(max_length=40, blank=True, verbose_name='screen diagonal')
    resolution = models.CharField(max_length=80, blank=True, verbose_name='resolution')
    touchscreen_type = models.CharField(
        max_length=20,
        choices=TouchscreenType,
        default=TouchscreenType.NONE,
        verbose_name='touchscreen type',
    )

    class Meta:
        verbose_name = 'product display specification'
        verbose_name_plural = 'product display specifications'

    def __str__(self) -> str:
        return f'Display: {self.product.sku}'
