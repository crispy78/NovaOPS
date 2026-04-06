from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Sum

from audit.services import log_event
from catalog.models import Product
from relations.models import Organization

from .models import (
    Cart,
    CartLine,
    FulfillmentOrder,
    FulfillmentOrderLine,
    FulfillmentOrderStatus,
    Invoice,
    InvoiceLine,
    InvoicePayment,
    InvoiceStatus,
    OrderLine,
    OrderStatus,
    Quote,
    QuoteLine,
    QuoteStatus,
    SalesOrder,
    Shipment,
    ShipmentLine,
    ShipmentStatus,
    ShippingOrder,
    ShippingOrderLine,
    ShippingOrderStatus,
    next_fulfillment_reference,
    next_invoice_reference,
    next_order_reference,
    next_quote_reference,
    next_shipping_order_reference,
    snapshot_line_from_product,
)


def get_or_create_cart(user) -> Cart:
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


@transaction.atomic
def add_to_cart(*, user, product: Product, quantity: int, request=None) -> CartLine:
    cart = get_or_create_cart(user)
    line, created = CartLine.objects.get_or_create(cart=cart, product=product, defaults={'quantity': quantity})
    if not created:
        line.quantity += quantity
        line.save()
    log_event(
        action='cart.line_added',
        entity_type='Cart',
        entity_id=cart.id,
        request=request,
        metadata={'product_id': str(product.id), 'sku': product.sku, 'quantity': line.quantity},
    )
    return line


@transaction.atomic
def set_cart_line_quantity(*, user, line_id, quantity: int, request=None) -> None:
    cart = get_or_create_cart(user)
    line = CartLine.objects.select_related('product').get(pk=line_id, cart=cart)
    if quantity <= 0:
        sku = line.product.sku
        product_id = str(line.product_id)
        line.delete()
        log_event(
            action='cart.line_removed',
            entity_type='Cart',
            entity_id=cart.id,
            request=request,
            metadata={'product_id': product_id, 'sku': sku},
        )
        return

    line.quantity = quantity
    line.save(update_fields=['quantity'])
    log_event(
        action='cart.line_quantity_set',
        entity_type='Cart',
        entity_id=cart.id,
        request=request,
        metadata={'product_id': str(line.product_id), 'sku': line.product.sku, 'quantity': line.quantity},
    )


@transaction.atomic
def create_quote_from_cart(
    *,
    user,
    relation_organization: Organization,
    internal_reference: str = '',
    external_reference: str = '',
    request=None,
) -> Quote:
    cart = get_or_create_cart(user)
    lines = list(cart.lines.select_related('product'))
    if not lines:
        raise ValueError('Cart is empty')

    ref = next_quote_reference()
    quote = Quote(
        created_by=user,
        reference=ref,
        relation_organization=relation_organization,
        internal_reference=(internal_reference or '').strip()[:80],
        external_reference=(external_reference or '').strip()[:80],
    )
    try:
        quote.full_clean()
    except ValidationError as exc:
        raise ValueError('; '.join(exc.messages)) from exc
    quote.save()
    for i, cl in enumerate(lines):
        p = cl.product
        data = snapshot_line_from_product(p, cl.quantity, sort_order=i)
        QuoteLine.objects.create(quote=quote, **data)

    log_event(
        action='quote.created',
        entity_type='Quote',
        entity_id=quote.id,
        request=request,
        metadata={
            'reference': quote.reference,
            'lines': len(lines),
            'relation_organization_id': str(relation_organization.id),
        },
    )

    cart.lines.all().delete()
    log_event(
        action='cart.cleared',
        entity_type='Cart',
        entity_id=cart.id,
        request=request,
        metadata={'reason': 'converted_to_quote', 'quote_id': str(quote.id)},
    )
    return quote


@transaction.atomic
def create_order_from_cart(
    *,
    user,
    relation_organization: Organization | None = None,
    request=None,
) -> SalesOrder:
    cart = get_or_create_cart(user)
    lines = list(cart.lines.select_related('product'))
    if not lines:
        raise ValueError('Cart is empty')
    if relation_organization is None:
        raise ValueError('A customer or prospect organization is required.')

    ref = next_order_reference()
    order = SalesOrder.objects.create(
        created_by=user,
        reference=ref,
        relation_organization=relation_organization,
    )
    for i, cl in enumerate(lines):
        p = cl.product
        data = snapshot_line_from_product(p, cl.quantity, sort_order=i)
        OrderLine.objects.create(order=order, **data)

    log_event(
        action='order.created',
        entity_type='SalesOrder',
        entity_id=order.id,
        request=request,
        metadata={'reference': order.reference, 'lines': len(lines)},
    )

    cart.lines.all().delete()
    log_event(
        action='cart.cleared',
        entity_type='Cart',
        entity_id=cart.id,
        request=request,
        metadata={'reason': 'converted_to_order', 'order_id': str(order.id)},
    )
    return order


@transaction.atomic
def refresh_quote_prices_from_catalog(quote: Quote, *, request=None) -> int:
    """Update each line from live Product list price. Returns number of lines updated."""
    n = 0
    for line in quote.lines.select_related('product'):
        if line.product_id is None:
            continue
        p = line.product
        line.unit_price = p.list_price if p.list_price is not None else Decimal('0')
        line.currency = p.currency
        line.product_name = p.name
        line.sku = p.sku
        line.brand = p.brand or ''
        line.line_total = line.unit_price * line.quantity
        line.save()
        n += 1
    log_event(
        action='quote.prices_refreshed',
        entity_type='Quote',
        entity_id=quote.id,
        request=request,
        metadata={'reference': quote.reference, 'lines_updated': n},
    )
    return n


@transaction.atomic
def create_order_from_quote(*, quote: Quote, user, request=None) -> SalesOrder:
    if quote.is_locked:
        raise ValueError('This quote is already locked.')
    if quote.orders.exists():
        raise ValueError('An order already exists for this quote.')
    lines = list(quote.lines.select_related('product'))
    if not lines:
        raise ValueError('Quote has no lines.')

    ref = next_order_reference()
    order = SalesOrder.objects.create(
        created_by=user,
        reference=ref,
        quote=quote,
        relation_organization=quote.relation_organization,
        status=OrderStatus.CONFIRMED,
        notes=(f'From quote {quote.reference}.' + (f'\n\n{quote.notes}' if quote.notes else '')).strip(),
    )
    for i, ql in enumerate(lines):
        OrderLine.objects.create(
            order=order,
            product=ql.product,
            product_name=ql.product_name,
            sku=ql.sku,
            brand=ql.brand or '',
            quantity=ql.quantity,
            unit_price=ql.unit_price,
            currency=ql.currency,
            line_total=ql.line_total,
            sort_order=i,
        )

    quote.is_locked = True
    quote.status = QuoteStatus.ACCEPTED
    quote.save(update_fields=['is_locked', 'status', 'updated_at'])

    log_event(
        action='order.created_from_quote',
        entity_type='SalesOrder',
        entity_id=order.id,
        request=request,
        metadata={
            'reference': order.reference,
            'quote_id': str(quote.id),
            'quote_reference': quote.reference,
        },
    )
    log_event(
        action='quote.locked',
        entity_type='Quote',
        entity_id=quote.id,
        request=request,
        metadata={'reference': quote.reference, 'order_id': str(order.id)},
    )
    return order


@transaction.atomic
def create_invoice_from_order(*, order: SalesOrder, user, request=None) -> Invoice:
    if order.invoices.exclude(status=InvoiceStatus.CANCELLED).exists():
        raise ValueError(
            'This order already has an invoice. Cancel the existing invoice in Admin if you need to replace it.',
        )
    lines = list(order.lines.select_related('product'))
    if not lines:
        raise ValueError('Order has no lines.')

    ref = next_invoice_reference()
    currency = lines[0].currency
    invoice = Invoice.objects.create(
        reference=ref,
        order=order,
        created_by=user,
        relation_organization=order.relation_organization,
        status=InvoiceStatus.ISSUED,
        currency=currency,
    )
    for i, ol in enumerate(lines):
        InvoiceLine.objects.create(
            invoice=invoice,
            product=ol.product,
            product_name=ol.product_name,
            sku=ol.sku,
            brand=ol.brand or '',
            quantity=ol.quantity,
            unit_price=ol.unit_price,
            currency=ol.currency,
            line_total=ol.line_total,
            sort_order=i,
        )

    log_event(
        action='invoice.created',
        entity_type='Invoice',
        entity_id=invoice.id,
        request=request,
        metadata={'reference': invoice.reference, 'order_id': str(order.id)},
    )
    return invoice


@transaction.atomic
def add_invoice_payment(
    *,
    invoice: Invoice,
    amount: Decimal,
    reference_note: str,
    user,
    request=None,
) -> InvoicePayment:
    if invoice.status == InvoiceStatus.CANCELLED:
        raise ValueError('Cannot record payments on a cancelled invoice.')
    balance = invoice.balance_due()
    if balance <= 0:
        raise ValueError('This invoice is already paid in full.')
    if amount > balance:
        raise ValueError(f'Payment cannot exceed balance due ({balance} {invoice.currency}).')

    payment = InvoicePayment(
        invoice=invoice,
        amount=amount,
        reference_note=(reference_note or '').strip()[:120],
        created_by=user,
    )
    payment.full_clean()
    payment.save()

    log_event(
        action='invoice.payment_recorded',
        entity_type='Invoice',
        entity_id=invoice.id,
        request=request,
        metadata={
            'reference': invoice.reference,
            'amount': str(amount),
            'balance_after': str(invoice.balance_due()),
        },
    )
    return payment


@transaction.atomic
def create_fulfillment_order_from_sales_order(*, order: SalesOrder, user, request=None) -> FulfillmentOrder:
    """Create a fulfillment order (warehouse pick doc) from a sales order; lines snapshot qty and locations."""
    if order.status == OrderStatus.CANCELLED:
        raise ValueError('Cannot create a fulfillment order for a cancelled sales order.')
    if order.fulfillment_orders.exclude(status=FulfillmentOrderStatus.CANCELLED).exists():
        raise ValueError(
            'This sales order already has a fulfillment order. Cancel the existing one in Admin if you need to replace it.',
        )
    lines = list(order.lines.select_related('product'))
    if not lines:
        raise ValueError('Order has no lines.')

    ref = next_fulfillment_reference()
    fo = FulfillmentOrder.objects.create(
        reference=ref,
        sales_order=order,
        created_by=user,
        status=FulfillmentOrderStatus.PENDING,
    )
    for i, ol in enumerate(lines):
        wh_loc = ''
        if ol.product_id:
            wh_loc = (ol.product.warehouse_location or '')[:120]
        FulfillmentOrderLine.objects.create(
            fulfillment_order=fo,
            product=ol.product,
            product_name=ol.product_name,
            sku=ol.sku,
            brand=ol.brand or '',
            quantity=ol.quantity,
            warehouse_location=wh_loc,
            sort_order=i,
        )

    log_event(
        action='fulfillment_order.created',
        entity_type='FulfillmentOrder',
        entity_id=fo.id,
        request=request,
        metadata={'reference': fo.reference, 'sales_order_id': str(order.id), 'lines': len(lines)},
    )
    return fo


def fulfillment_line_unallocated_quantity(fo_line: FulfillmentOrderLine) -> int:
    """How many units of this fulfillment line are not yet on a non-cancelled shipping order."""
    allocated = (
        ShippingOrderLine.objects.filter(fulfillment_line=fo_line)
        .exclude(shipping_order__status=ShippingOrderStatus.CANCELLED)
        .aggregate(s=Sum('quantity'))
    )
    return fo_line.quantity - (allocated['s'] or 0)


def shipping_order_line_unshipped_quantity(sol: ShippingOrderLine) -> int:
    """How many units of this shipping order line are not yet on a non-cancelled shipment."""
    shipped = (
        ShipmentLine.objects.filter(shipping_order_line=sol)
        .exclude(shipment__status=ShipmentStatus.CANCELLED)
        .aggregate(s=Sum('quantity'))
    )
    return sol.quantity - (shipped['s'] or 0)


def refresh_shipping_order_status(shipping_order: ShippingOrder) -> None:
    """Set status from shipment line coverage (ignores cancelled shipments)."""
    if shipping_order.status == ShippingOrderStatus.CANCELLED:
        return
    lines = list(shipping_order.lines.all())
    if not lines:
        shipping_order.status = ShippingOrderStatus.RELEASED
        shipping_order.save(update_fields=['status', 'updated_at'])
        return
    all_fully_shipped = True
    any_shipped = False
    for line in lines:
        shipped = (
            ShipmentLine.objects.filter(shipping_order_line=line)
            .exclude(shipment__status=ShipmentStatus.CANCELLED)
            .aggregate(s=Sum('quantity'))
        )
        n = shipped['s'] or 0
        if n < line.quantity:
            all_fully_shipped = False
        if n > 0:
            any_shipped = True
    if all_fully_shipped:
        shipping_order.status = ShippingOrderStatus.SHIPPED
    elif any_shipped:
        shipping_order.status = ShippingOrderStatus.PARTIALLY_SHIPPED
    else:
        shipping_order.status = ShippingOrderStatus.RELEASED
    shipping_order.save(update_fields=['status', 'updated_at'])


@transaction.atomic
def create_shipping_order_from_fulfillment(
    *,
    fulfillment_order: FulfillmentOrder,
    user,
    quantities_by_line_id: dict,
    notes: str = '',
    request=None,
) -> ShippingOrder:
    """Create a shipping order with lines; quantities map fulfillment line UUID -> qty to allocate."""
    fo = FulfillmentOrder.objects.select_for_update().get(pk=fulfillment_order.pk)
    if fo.status == FulfillmentOrderStatus.CANCELLED:
        raise ValueError('Cannot create a shipping order for a cancelled fulfillment order.')

    to_create: list[tuple[FulfillmentOrderLine, int]] = []
    for line_id, raw_qty in quantities_by_line_id.items():
        qty = int(raw_qty) if raw_qty is not None else 0
        if qty <= 0:
            continue
        fl = FulfillmentOrderLine.objects.get(pk=line_id, fulfillment_order=fo)
        rem = fulfillment_line_unallocated_quantity(fl)
        if qty > rem:
            raise ValueError(f'{fl.sku}: at most {rem} unit(s) still available to allocate.')
        to_create.append((fl, qty))

    if not to_create:
        raise ValueError('Enter a positive quantity for at least one line.')

    ref = next_shipping_order_reference()
    so = ShippingOrder.objects.create(
        reference=ref,
        fulfillment_order=fo,
        sales_order=fo.sales_order,
        created_by=user,
        status=ShippingOrderStatus.RELEASED,
        notes=(notes or '').strip(),
    )
    for fl, qty in to_create:
        ShippingOrderLine.objects.create(
            shipping_order=so,
            fulfillment_line=fl,
            quantity=qty,
        )

    log_event(
        action='shipping_order.created',
        entity_type='ShippingOrder',
        entity_id=so.id,
        request=request,
        metadata={
            'reference': so.reference,
            'fulfillment_order_id': str(fo.id),
            'sales_order_id': str(fo.sales_order_id),
            'lines': len(to_create),
        },
    )
    return so


@transaction.atomic
def create_shipment_for_shipping_order(
    *,
    shipping_order: ShippingOrder,
    user,
    carrier: str = '',
    tracking_number: str = '',
    lines_qty: dict,
    notes: str = '',
    request=None,
) -> Shipment:
    """Create one shipment and shipment lines; lines_qty maps shipping order line UUID -> qty."""
    sho = ShippingOrder.objects.select_for_update().get(pk=shipping_order.pk)
    if sho.status == ShippingOrderStatus.CANCELLED:
        raise ValueError('Cannot add a shipment to a cancelled shipping order.')

    seq = sho.shipments.aggregate(m=Max('sequence'))['m'] or 0
    seq += 1

    sh = Shipment.objects.create(
        shipping_order=sho,
        sequence=seq,
        carrier=(carrier or '').strip()[:120],
        tracking_number=(tracking_number or '').strip()[:120],
        notes=(notes or '').strip(),
        status=ShipmentStatus.PLANNED,
    )

    created_any = False
    for line_id, raw_qty in lines_qty.items():
        qty = int(raw_qty) if raw_qty is not None else 0
        if qty <= 0:
            continue
        sol = ShippingOrderLine.objects.get(pk=line_id, shipping_order=sho)
        unshipped = shipping_order_line_unshipped_quantity(sol)
        if qty > unshipped:
            raise ValueError(
                f'{sol.fulfillment_line.sku}: at most {unshipped} unit(s) left to put on this shipment.',
            )
        ShipmentLine.objects.create(
            shipment=sh,
            shipping_order_line=sol,
            quantity=qty,
        )
        created_any = True

    if not created_any:
        sh.delete()
        raise ValueError('Enter a positive quantity for at least one line on this shipment.')

    refresh_shipping_order_status(sho)

    log_event(
        action='shipment.created',
        entity_type='Shipment',
        entity_id=sh.id,
        request=request,
        metadata={
            'shipping_order_id': str(sho.id),
            'shipping_order_reference': sho.reference,
            'sequence': sh.sequence,
        },
    )
    return sh
