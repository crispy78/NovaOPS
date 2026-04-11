from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from catalog.models import Product
from core.models import UUIDPrimaryKeyModel

MONEY = dict(max_digits=12, decimal_places=2)


class Cart(UUIDPrimaryKeyModel):
    """One shopping cart per user (sales)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sales_cart',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'cart'
        verbose_name_plural = 'carts'

    def __str__(self) -> str:
        return f'Cart {self.user}'


class CartLine(UUIDPrimaryKeyModel):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey(
        Product, null=True, blank=True, on_delete=models.CASCADE, related_name='cart_lines',
    )
    quantity = models.PositiveIntegerField(default=1)
    parent_line = models.ForeignKey(
        'self',
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='option_lines',
        verbose_name='parent line',
    )
    product_option = models.ForeignKey(
        'catalog.ProductOption',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='cart_lines',
    )
    # Denormalized for inline (non-standalone) options:
    option_name = models.CharField(max_length=200, blank=True)
    option_sku = models.CharField(max_length=100, blank=True)
    option_price_delta = models.DecimalField(**MONEY, default=Decimal('0.00'))

    class Meta:
        constraints = [
            # Only one line per product per cart for top-level (non-option) lines.
            models.UniqueConstraint(
                fields=['cart', 'product'],
                condition=models.Q(parent_line__isnull=True),
                name='sales_cartline_unique_product_main',
            ),
        ]

    def __str__(self) -> str:
        if self.product_id:
            return f'{self.quantity}× {self.product.sku}'
        return f'{self.quantity}× {self.option_sku}'


class QuoteStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    SENT = 'sent', 'Sent'
    ACCEPTED = 'accepted', 'Accepted'
    CANCELLED = 'cancelled', 'Cancelled'
    EXPIRED = 'expired', 'Expired'


class Quote(UUIDPrimaryKeyModel):
    """Commercial quote; line items are snapshots taken when the quote is created (and editable)."""

    reference = models.CharField(max_length=32, unique=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='quotes_created',
    )
    relation_organization = models.ForeignKey(
        'relations.Organization',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='quotes',
        verbose_name='customer / prospect',
        help_text='Organization this quote is for (must be tagged as Customer or Prospect).',
    )
    internal_reference = models.CharField(
        max_length=80,
        blank=True,
        verbose_name='internal reference ID',
        help_text='Your internal reference (e.g. CRM deal ID).',
    )
    external_reference = models.CharField(
        max_length=80,
        blank=True,
        verbose_name='external reference ID',
        help_text='Customer or third-party reference (e.g. their RFQ number).',
    )
    status = models.CharField(max_length=20, choices=QuoteStatus, default=QuoteStatus.DRAFT, db_index=True)
    valid_until = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    is_locked = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name='locked',
        help_text='When true, the quote is frozen (typically after an order was created from it).',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'quote'
        verbose_name_plural = 'quotes'

    def __str__(self) -> str:
        return self.reference

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse('sales:quote_detail', kwargs={'pk': self.pk})

    def clean(self) -> None:
        super().clean()
        if self.relation_organization_id:
            org = self.relation_organization
            if not org.is_customer_or_prospect_relation():
                raise ValidationError(
                    {
                        'relation_organization': 'Quotes may only be linked to organizations tagged as Customer or Prospect.',
                    },
                )


class QuoteLine(UUIDPrimaryKeyModel):
    """Frozen commercial line; prices can be updated manually or refreshed from catalog."""

    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL, related_name='quote_lines')
    product_name = models.CharField(max_length=255)
    sku = models.CharField(max_length=64)
    brand = models.CharField(max_length=120, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(**MONEY)
    tax_rate_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name='tax rate (%)')
    currency = models.CharField(max_length=3, default='EUR')
    line_total = models.DecimalField(**MONEY)
    sort_order = models.PositiveSmallIntegerField(default=0)
    parent_line = models.ForeignKey(
        'self',
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='option_lines',
        verbose_name='parent line',
    )
    product_option = models.ForeignKey(
        'catalog.ProductOption',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='quote_lines',
    )

    class Meta:
        ordering = ['quote', 'sort_order', 'id']

    def __str__(self) -> str:
        return f'{self.sku} × {self.quantity}'


class OrderStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    CONFIRMED = 'confirmed', 'Confirmed'
    CANCELLED = 'cancelled', 'Cancelled'
    FULFILLED = 'fulfilled', 'Fulfilled'


class SalesOrder(UUIDPrimaryKeyModel):
    """Sales order created from cart (or optionally linked to an accepted quote later)."""

    reference = models.CharField(max_length=32, unique=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='sales_orders_created',
    )
    quote = models.ForeignKey(
        Quote,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='orders',
    )
    relation_organization = models.ForeignKey(
        'relations.Organization',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='sales_orders',
        verbose_name='customer / prospect',
        help_text='Copied from the quote when the order is created from a quote.',
    )
    status = models.CharField(max_length=20, choices=OrderStatus, default=OrderStatus.DRAFT, db_index=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'sales order'
        verbose_name_plural = 'sales orders'

    def __str__(self) -> str:
        return self.reference

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse('sales:order_detail', kwargs={'pk': self.pk})


class OrderLine(UUIDPrimaryKeyModel):
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL, related_name='order_lines')
    product_name = models.CharField(max_length=255)
    sku = models.CharField(max_length=64)
    brand = models.CharField(max_length=120, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(**MONEY)
    tax_rate_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name='tax rate (%)')
    currency = models.CharField(max_length=3, default='EUR')
    line_total = models.DecimalField(**MONEY)
    sort_order = models.PositiveSmallIntegerField(default=0)
    parent_line = models.ForeignKey(
        'self',
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='option_lines',
        verbose_name='parent line',
    )
    product_option = models.ForeignKey(
        'catalog.ProductOption',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='order_lines',
    )

    class Meta:
        ordering = ['order', 'sort_order', 'id']

    def __str__(self) -> str:
        return f'{self.sku} × {self.quantity}'


class InvoiceStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    ISSUED = 'issued', 'Issued'
    CANCELLED = 'cancelled', 'Cancelled'


class Invoice(UUIDPrimaryKeyModel):
    """Invoice for a sales order; lines are a snapshot at issue time. Payments recorded until paid in full."""

    reference = models.CharField(max_length=32, unique=True, db_index=True)
    order = models.ForeignKey(
        SalesOrder,
        on_delete=models.PROTECT,
        related_name='invoices',
        verbose_name='sales order',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='invoices_created',
    )
    relation_organization = models.ForeignKey(
        'relations.Organization',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='invoices',
        verbose_name='bill-to organization',
    )
    status = models.CharField(
        max_length=20,
        choices=InvoiceStatus,
        default=InvoiceStatus.ISSUED,
        db_index=True,
    )
    currency = models.CharField(max_length=3, default='EUR')
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'invoice'
        verbose_name_plural = 'invoices'

    def __str__(self) -> str:
        return self.reference

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse('sales:invoice_detail', kwargs={'pk': self.pk})

    def total(self) -> Decimal:
        """Subtotal excluding VAT."""
        from django.db.models import Sum

        agg = self.lines.aggregate(s=Sum('line_total'))
        return agg['s'] if agg['s'] is not None else Decimal('0')

    def tax_total(self) -> Decimal:
        """Total VAT amount across all lines."""
        from collections import defaultdict
        buckets: dict = defaultdict(Decimal)
        for line in self.lines.all():
            if line.tax_rate_pct:
                buckets[line.tax_rate_pct] += line.line_total
        if not buckets:
            return Decimal('0')
        return sum(
            (base * rate / 100).quantize(Decimal('0.01'))
            for rate, base in buckets.items()
        )

    def grand_total(self) -> Decimal:
        """Total including VAT — the amount the customer pays."""
        return self.total() + self.tax_total()

    def amount_paid(self) -> Decimal:
        from django.db.models import Sum

        agg = self.payments.aggregate(s=Sum('amount'))
        return agg['s'] if agg['s'] is not None else Decimal('0')

    def balance_due(self) -> Decimal:
        return self.grand_total() - self.amount_paid()

    def is_paid_in_full(self) -> bool:
        return self.balance_due() <= Decimal('0')


class InvoiceLine(UUIDPrimaryKeyModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL, related_name='invoice_lines')
    product_name = models.CharField(max_length=255)
    sku = models.CharField(max_length=64)
    brand = models.CharField(max_length=120, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(**MONEY)
    tax_rate_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name='tax rate (%)')
    currency = models.CharField(max_length=3, default='EUR')
    line_total = models.DecimalField(**MONEY)
    sort_order = models.PositiveSmallIntegerField(default=0)
    parent_line = models.ForeignKey(
        'self',
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='option_lines',
        verbose_name='parent line',
    )
    product_option = models.ForeignKey(
        'catalog.ProductOption',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='invoice_lines',
    )

    class Meta:
        ordering = ['invoice', 'sort_order', 'id']

    def __str__(self) -> str:
        return f'{self.sku} × {self.quantity}'


class InvoicePayment(UUIDPrimaryKeyModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(**MONEY)
    reference_note = models.CharField(
        max_length=120,
        blank=True,
        verbose_name='payment reference',
        help_text='e.g. bank reference, check number.',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='invoice_payments_recorded',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['invoice', 'created_at']
        verbose_name = 'invoice payment'
        verbose_name_plural = 'invoice payments'

    def __str__(self) -> str:
        return f'{self.amount} on {self.invoice.reference}'

    def clean(self) -> None:
        super().clean()
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({'amount': 'Payment amount must be greater than zero.'})


class FulfillmentOrderStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    IN_PROGRESS = 'in_progress', 'In progress'
    COMPLETED = 'completed', 'Completed'
    CANCELLED = 'cancelled', 'Cancelled'


class FulfillmentOrder(UUIDPrimaryKeyModel):
    """What the warehouse picks against: created from a sales order (pick list / internal ship doc)."""

    reference = models.CharField(max_length=32, unique=True, db_index=True)
    sales_order = models.ForeignKey(
        SalesOrder,
        on_delete=models.PROTECT,
        related_name='fulfillment_orders',
        verbose_name='sales order',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='fulfillment_orders_created',
    )
    status = models.CharField(
        max_length=20,
        choices=FulfillmentOrderStatus,
        default=FulfillmentOrderStatus.PENDING,
        db_index=True,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'fulfillment order'
        verbose_name_plural = 'fulfillment orders'

    def __str__(self) -> str:
        return self.reference

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse('sales:fulfillment_detail', kwargs={'pk': self.pk})


class FulfillmentOrderLine(UUIDPrimaryKeyModel):
    fulfillment_order = models.ForeignKey(
        FulfillmentOrder,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    product = models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='fulfillment_order_lines',
    )
    product_name = models.CharField(max_length=255)
    sku = models.CharField(max_length=64)
    brand = models.CharField(max_length=120, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    warehouse_location = models.CharField(
        max_length=120,
        blank=True,
        verbose_name='warehouse location',
        help_text='Bin/aisle snapshot from the product when this line was created.',
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    parent_line = models.ForeignKey(
        'self',
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='option_lines',
        verbose_name='parent line',
    )

    class Meta:
        ordering = ['fulfillment_order', 'sort_order', 'id']


class ShippingOrderStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    RELEASED = 'released', 'Released'
    PARTIALLY_SHIPPED = 'partially_shipped', 'Partially shipped'
    SHIPPED = 'shipped', 'Shipped'
    CANCELLED = 'cancelled', 'Cancelled'


class ShippingOrder(UUIDPrimaryKeyModel):
    """Outbound customer shipment document; may cover only part of a fulfillment order."""

    reference = models.CharField(max_length=32, unique=True, db_index=True)
    fulfillment_order = models.ForeignKey(
        FulfillmentOrder,
        on_delete=models.PROTECT,
        related_name='shipping_orders',
        verbose_name='fulfillment order',
    )
    sales_order = models.ForeignKey(
        SalesOrder,
        on_delete=models.PROTECT,
        related_name='shipping_orders',
        verbose_name='sales order',
        help_text='Denormalized from the fulfillment order for reporting and navigation.',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='shipping_orders_created',
    )
    status = models.CharField(
        max_length=24,
        choices=ShippingOrderStatus,
        default=ShippingOrderStatus.RELEASED,
        db_index=True,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'shipping order'
        verbose_name_plural = 'shipping orders'

    def __str__(self) -> str:
        return self.reference

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse('sales:shipping_detail', kwargs={'pk': self.pk})


class ShippingOrderLine(UUIDPrimaryKeyModel):
    shipping_order = models.ForeignKey(
        ShippingOrder,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    fulfillment_line = models.ForeignKey(
        FulfillmentOrderLine,
        on_delete=models.PROTECT,
        related_name='shipping_lines',
        verbose_name='fulfillment line',
    )
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['shipping_order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['shipping_order', 'fulfillment_line'],
                name='sales_shippingorderline_unique_fulfillment_line_per_order',
            ),
        ]


class ShipmentStatus(models.TextChoices):
    PLANNED = 'planned', 'Planned'
    IN_TRANSIT = 'in_transit', 'In transit'
    DELIVERED = 'delivered', 'Delivered'
    CANCELLED = 'cancelled', 'Cancelled'


class Shipment(UUIDPrimaryKeyModel):
    """One physical dispatch (parcel, pallet, etc.) under a shipping order."""

    shipping_order = models.ForeignKey(
        ShippingOrder,
        on_delete=models.CASCADE,
        related_name='shipments',
    )
    sequence = models.PositiveSmallIntegerField(
        default=1,
        help_text='Display order within the shipping order (1 = first shipment).',
    )
    carrier = models.CharField(max_length=120, blank=True)
    tracking_number = models.CharField(max_length=120, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=ShipmentStatus,
        default=ShipmentStatus.PLANNED,
        db_index=True,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['shipping_order', 'sequence', 'id']
        verbose_name = 'shipment'
        verbose_name_plural = 'shipments'

    def __str__(self) -> str:
        return f'{self.shipping_order.reference} · #{self.sequence}'


class ShipmentLine(UUIDPrimaryKeyModel):
    shipment = models.ForeignKey(
        Shipment,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    shipping_order_line = models.ForeignKey(
        ShippingOrderLine,
        on_delete=models.PROTECT,
        related_name='shipment_lines',
        verbose_name='shipping order line',
    )
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['shipment', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['shipment', 'shipping_order_line'],
                name='sales_shipmentline_unique_line_per_shipment',
            ),
        ]


class CreditNote(UUIDPrimaryKeyModel):
    """Credit note issued against an invoice to reduce the amount owed."""

    reference = models.CharField(max_length=32, unique=True, db_index=True)
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name='credit_notes',
        verbose_name='invoice',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='credit_notes_created',
    )
    relation_organization = models.ForeignKey(
        'relations.Organization',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='credit_notes',
        verbose_name='organization',
    )
    currency = models.CharField(max_length=3, default='EUR')
    reason = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='reason',
        help_text='Short reason for issuing this credit note.',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'credit note'
        verbose_name_plural = 'credit notes'

    def __str__(self) -> str:
        return self.reference

    def get_absolute_url(self) -> str:
        from django.urls import reverse
        return reverse('sales:credit_note_detail', kwargs={'pk': self.pk})

    def total(self) -> Decimal:
        from django.db.models import Sum
        agg = self.lines.aggregate(s=Sum('line_total'))
        return agg['s'] if agg['s'] is not None else Decimal('0')


class CreditNoteLine(UUIDPrimaryKeyModel):
    credit_note = models.ForeignKey(CreditNote, on_delete=models.CASCADE, related_name='lines')
    invoice_line = models.ForeignKey(
        InvoiceLine,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='credit_note_lines',
        verbose_name='invoice line',
    )
    product_name = models.CharField(max_length=255)
    sku = models.CharField(max_length=64, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(**MONEY)
    tax_rate_pct = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, verbose_name='tax rate (%)'
    )
    currency = models.CharField(max_length=3, default='EUR')
    line_total = models.DecimalField(**MONEY)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['credit_note', 'sort_order', 'id']

    def __str__(self) -> str:
        return f'{self.sku} × {self.quantity}'


def next_credit_note_reference() -> str:
    from core.models import next_reference
    return next_reference('CN', timezone.now().year)


def next_quote_reference() -> str:
    from core.models import next_reference
    return next_reference('Q', timezone.now().year)


def next_order_reference() -> str:
    from core.models import next_reference
    return next_reference('SO', timezone.now().year)


def next_invoice_reference() -> str:
    from core.models import next_reference
    return next_reference('INV', timezone.now().year)


def next_fulfillment_reference() -> str:
    from core.models import next_reference
    return next_reference('FO', timezone.now().year)


def next_shipping_order_reference() -> str:
    from core.models import next_reference
    return next_reference('SHP', timezone.now().year)


def snapshot_line_from_product(product: Product, quantity: int, sort_order: int = 0) -> dict:
    unit = product.list_price if product.list_price is not None else Decimal('0')
    tax_pct = product.tax_rate.rate if product.tax_rate_id else None
    return {
        'product': product,
        'product_name': product.name,
        'sku': product.sku,
        'brand': product.brand or '',
        'quantity': quantity,
        'unit_price': unit,
        'tax_rate_pct': tax_pct,
        'currency': product.currency,
        'line_total': unit * quantity,
        'sort_order': sort_order,
    }


def snapshot_option_from_cart_line(cart_line: 'CartLine', *, sort_order: int = 0, parent_currency: str = 'EUR') -> dict:
    """Build a document-line snapshot dict for a CartLine that is an option child."""
    if cart_line.product_id:
        p = cart_line.product
        unit = p.list_price if p.list_price is not None else Decimal('0')
        return {
            'product': p,
            'product_name': p.name,
            'sku': p.sku,
            'brand': p.brand or '',
            'quantity': cart_line.quantity,
            'unit_price': unit,
            'currency': p.currency,
            'line_total': unit * cart_line.quantity,
            'sort_order': sort_order,
            'product_option': cart_line.product_option,
        }
    unit = cart_line.option_price_delta or Decimal('0')
    return {
        'product': None,
        'product_name': cart_line.option_name,
        'sku': cart_line.option_sku,
        'brand': '',
        'quantity': cart_line.quantity,
        'unit_price': unit,
        'currency': parent_currency,
        'line_total': unit * cart_line.quantity,
        'sort_order': sort_order,
        'product_option': cart_line.product_option,
    }
