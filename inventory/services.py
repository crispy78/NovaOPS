from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from .models import MovementType, StockEntry, StockMovement


@transaction.atomic
def decrement_stock_for_fulfillment(fulfillment_order, user) -> int:
    """
    Decrement inventory for every line in a FulfillmentOrder.

    Stock is deducted from whichever StockEntry has the highest quantity on hand
    for each product. If no stock entry exists the decrement is skipped (stock
    cannot go below zero at any individual location in this pass).

    Returns the number of lines for which stock was decremented.
    """
    decremented = 0
    for line in fulfillment_order.lines.select_related('product').all():
        product = line.product
        if product is None or not product.inventory_tracked:
            continue
        qty_needed = Decimal(str(line.quantity))
        # Pick the location with the most stock to drain from first.
        entries = (
            StockEntry.objects
            .select_for_update()
            .filter(product=product, quantity_on_hand__gt=0)
            .order_by('-quantity_on_hand')
        )
        for entry in entries:
            if qty_needed <= 0:
                break
            take = min(entry.quantity_on_hand, qty_needed)
            entry.quantity_on_hand -= take
            entry.save(update_fields=['quantity_on_hand', 'last_updated'])
            StockMovement.objects.create(
                product=product,
                location=entry.location,
                delta=-take,
                movement_type=MovementType.SHIPMENT,
                reference=fulfillment_order.reference,
                created_by=user,
            )
            qty_needed -= take
        decremented += 1
    return decremented


@transaction.atomic
def adjust_stock(product, location, delta: Decimal, notes: str, user) -> StockEntry:
    """
    Apply a manual stock adjustment (positive or negative).

    Returns the updated StockEntry.
    """
    entry, _ = StockEntry.objects.select_for_update().get_or_create(
        product=product,
        location=location,
        defaults={'quantity_on_hand': Decimal('0')},
    )
    entry.quantity_on_hand += delta
    entry.save(update_fields=['quantity_on_hand', 'last_updated'])
    StockMovement.objects.create(
        product=product,
        location=location,
        delta=delta,
        movement_type=MovementType.ADJUSTMENT,
        notes=notes,
        created_by=user,
    )
    return entry
