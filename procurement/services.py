from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from inventory.models import MovementType, StockEntry, StockMovement
from .models import POStatus, PurchaseOrder, PurchaseOrderLine


@transaction.atomic
def receive_lines(po: PurchaseOrder, receipts: list[dict], user) -> None:
    """
    Mark goods as received against a PurchaseOrder and update stock.

    receipts: list of dicts with keys:
        po_line  – PurchaseOrderLine instance
        qty      – Decimal quantity to receive (must be > 0)
        location – StockLocation instance (destination)
        notes    – optional str
    """
    for r in receipts:
        po_line: PurchaseOrderLine = r['po_line']
        qty: Decimal = r['qty']
        location = r['location']
        notes: str = r.get('notes', '')

        if qty <= 0:
            continue

        # Cap at outstanding so we don't over-receive accidentally
        qty = min(qty, po_line.qty_outstanding)
        if qty <= 0:
            continue

        po_line.qty_received = po_line.qty_received + qty
        po_line.save(update_fields=['qty_received'])

        # Upsert StockEntry
        entry, _ = StockEntry.objects.select_for_update().get_or_create(
            product=po_line.product,
            location=location,
            defaults={'quantity_on_hand': Decimal('0')},
        )
        entry.quantity_on_hand += qty
        entry.save(update_fields=['quantity_on_hand', 'last_updated'])

        StockMovement.objects.create(
            product=po_line.product,
            location=location,
            delta=qty,
            movement_type=MovementType.RECEIPT,
            reference=po.ref,
            notes=notes,
            created_by=user,
        )

    # Refresh lines to recompute status
    lines = list(po.lines.all())
    if all(ln.qty_received >= ln.qty_ordered for ln in lines):
        po.status = POStatus.RECEIVED
    elif any(ln.qty_received > 0 for ln in lines):
        po.status = POStatus.PARTIAL
    po.save(update_fields=['status'])
