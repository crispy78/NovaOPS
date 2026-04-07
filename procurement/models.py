from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import UUIDPrimaryKeyModel

MONEY = dict(max_digits=12, decimal_places=2)
STOCK_QTY = dict(max_digits=12, decimal_places=3)


class POStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    SENT = 'sent', 'Sent'
    PARTIAL = 'partial', 'Partially received'
    RECEIVED = 'received', 'Fully received'
    CANCELLED = 'cancelled', 'Cancelled'


class PurchaseOrder(UUIDPrimaryKeyModel):
    ref = models.CharField(max_length=30, unique=True, editable=False)
    supplier = models.ForeignKey(
        'relations.Organization',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='purchase_orders',
    )
    status = models.CharField(max_length=20, choices=POStatus.choices, default=POStatus.DRAFT)
    expected_delivery_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='+',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'purchase order'
        verbose_name_plural = 'purchase orders'

    def __str__(self) -> str:
        return self.ref

    def save(self, *args, **kwargs) -> None:
        if not self.ref:
            from core.models import next_reference
            self.ref = next_reference('PO', timezone.now().year)
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        from django.urls import reverse
        return reverse('procurement:po_detail', kwargs={'pk': self.pk})

    @property
    def total_cost(self) -> Decimal | None:
        lines = list(self.lines.all())
        if not lines:
            return Decimal('0.00')
        totals = [ln.line_total for ln in lines]
        if any(t is None for t in totals):
            return None
        return sum(totals, Decimal('0.00'))

    @property
    def is_editable(self) -> bool:
        return self.status in (POStatus.DRAFT, POStatus.SENT)

    @property
    def can_receive(self) -> bool:
        return self.status in (POStatus.SENT, POStatus.PARTIAL, POStatus.DRAFT)


class PurchaseOrderLine(UUIDPrimaryKeyModel):
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name='lines',
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        related_name='purchase_order_lines',
    )
    description = models.CharField(max_length=500, blank=True)
    qty_ordered = models.DecimalField(**STOCK_QTY)
    unit_cost = models.DecimalField(**MONEY, null=True, blank=True)
    qty_received = models.DecimalField(**STOCK_QTY, default=Decimal('0'))

    class Meta:
        verbose_name = 'purchase order line'
        verbose_name_plural = 'purchase order lines'

    def __str__(self) -> str:
        return f'{self.purchase_order.ref} / {self.product.sku}'

    @property
    def qty_outstanding(self) -> Decimal:
        return self.qty_ordered - self.qty_received

    @property
    def line_total(self) -> Decimal | None:
        if self.unit_cost is None:
            return None
        return self.qty_ordered * self.unit_cost

    @property
    def display_name(self) -> str:
        return self.description or self.product.name
