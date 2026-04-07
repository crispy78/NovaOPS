from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models

from core.models import UUIDPrimaryKeyModel

STOCK_QTY = dict(max_digits=12, decimal_places=3)


class Warehouse(UUIDPrimaryKeyModel):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)
    address_line1 = models.CharField(max_length=200, blank=True)
    address_line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'warehouse'
        verbose_name_plural = 'warehouses'

    def __str__(self) -> str:
        return f'{self.code} – {self.name}'

    def get_absolute_url(self) -> str:
        from django.urls import reverse
        return reverse('inventory:warehouse_detail', kwargs={'pk': self.pk})


class StockLocation(UUIDPrimaryKeyModel):
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='locations')
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50)  # e.g. A-01-02, Shelf 3B
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['warehouse', 'code']
        unique_together = [('warehouse', 'code')]
        verbose_name = 'stock location'
        verbose_name_plural = 'stock locations'

    def __str__(self) -> str:
        return f'{self.warehouse.code} / {self.code}'


class MovementType(models.TextChoices):
    RECEIPT = 'receipt', 'Purchase receipt'
    SHIPMENT = 'shipment', 'Shipment'
    ADJUSTMENT = 'adjustment', 'Manual adjustment'
    TRANSFER_IN = 'transfer_in', 'Transfer in'
    TRANSFER_OUT = 'transfer_out', 'Transfer out'
    RETURN = 'return', 'Customer return'


class StockEntry(UUIDPrimaryKeyModel):
    """Denormalised current stock level for a product at a location. Updated on every movement."""

    product = models.ForeignKey(
        'catalog.Product', on_delete=models.CASCADE, related_name='stock_entries',
    )
    location = models.ForeignKey(
        StockLocation, on_delete=models.CASCADE, related_name='stock_entries',
    )
    quantity_on_hand = models.DecimalField(**STOCK_QTY, default=Decimal('0'))
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('product', 'location')]
        verbose_name = 'stock entry'
        verbose_name_plural = 'stock entries'

    def __str__(self) -> str:
        return f'{self.product.sku} @ {self.location} = {self.quantity_on_hand}'


class StockMovement(UUIDPrimaryKeyModel):
    """Append-only audit log of every stock delta."""

    product = models.ForeignKey(
        'catalog.Product', on_delete=models.PROTECT, related_name='stock_movements',
    )
    location = models.ForeignKey(
        StockLocation, on_delete=models.PROTECT, related_name='stock_movements',
    )
    delta = models.DecimalField(**STOCK_QTY)  # positive = stock in, negative = stock out
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    reference = models.CharField(max_length=200, blank=True)  # e.g. PO-2026-00001
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
        verbose_name = 'stock movement'
        verbose_name_plural = 'stock movements'

    def __str__(self) -> str:
        sign = '+' if self.delta >= 0 else ''
        return f'{self.product.sku} {sign}{self.delta} @ {self.location}'
