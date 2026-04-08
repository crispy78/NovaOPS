from __future__ import annotations

import csv
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Prefetch, Sum, Value
from django.db.models.functions import Coalesce
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from catalog.models import Product

from audit.services import log_event

from .forms import (
    AddToCartForm,
    CartLineQuantityForm,
    CreateOrderFromCartForm,
    CreateQuoteFromCartForm,
    InvoicePaymentForm,
    QuoteHeaderForm,
    QuoteLineFormSet,
    ShipmentHeaderForm,
    make_create_shipping_order_form,
    make_shipment_lines_form,
)
from .list_filtering import (
    apply_reference_icontains,
    apply_relation_org_in,
    apply_status,
    sales_list_filter_context,
)
from .models import (
    CartLine,
    CreditNote,
    CreditNoteLine,
    FulfillmentOrder,
    FulfillmentOrderStatus,
    Invoice,
    InvoiceStatus,
    OrderStatus,
    Quote,
    QuoteStatus,
    SalesOrder,
    ShipmentStatus,
    ShippingOrder,
    ShippingOrderStatus,
    next_credit_note_reference,
)
from .services import (
    add_invoice_payment,
    add_to_cart,
    add_to_cart_with_options,
    create_fulfillment_order_from_sales_order,
    create_invoice_from_order,
    create_order_from_cart,
    create_order_from_quote,
    create_quote_from_cart,
    create_shipment_for_shipping_order,
    create_shipping_order_from_fulfillment,
    fulfillment_line_unallocated_quantity,
    get_or_create_cart,
    refresh_quote_prices_from_catalog,
    set_cart_line_quantity,
)


def _tax_breakdown(lines):
    """
    Given a list/queryset of document lines (QuoteLine / OrderLine / InvoiceLine),
    return a list of dicts: [{'rate': Decimal, 'base': Decimal, 'tax': Decimal}, ...]
    sorted by rate. Lines without a tax_rate_pct are grouped under rate=None.
    """
    from collections import defaultdict
    buckets = defaultdict(Decimal)
    for line in lines:
        rate = getattr(line, 'tax_rate_pct', None)
        buckets[rate] += line.line_total
    result = []
    for rate, base in sorted(buckets.items(), key=lambda x: (x[0] is None, x[0] or 0)):
        tax = (base * rate / 100).quantize(Decimal('0.01')) if rate is not None else Decimal('0')
        result.append({'rate': rate, 'base': base, 'tax': tax})
    return result


class CartAddView(LoginRequiredMixin, View):
    def post(self, request, product_pk, *args, **kwargs):
        product = get_object_or_404(Product, pk=product_pk)
        form = AddToCartForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Enter a valid quantity.')
            return redirect(product.get_absolute_url())

        quantity = form.cleaned_data['quantity']
        selected_option_pks = request.POST.getlist('option_pks')

        if selected_option_pks:
            add_to_cart_with_options(
                user=request.user,
                product=product,
                quantity=quantity,
                selected_option_pks=selected_option_pks,
                request=request,
            )
        else:
            add_to_cart(user=request.user, product=product, quantity=quantity, request=request)

        messages.success(request, f'Added {quantity} item(s) to your cart.')
        return redirect(product.get_absolute_url())


class CartView(LoginRequiredMixin, TemplateView):
    template_name = 'sales/cart.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        cart = get_or_create_cart(self.request.user)
        from catalog.models import ProductImage
        from .models import CartLine as CL
        money = DecimalField(max_digits=14, decimal_places=2)
        main_lines = list(
            cart.lines
            .filter(parent_line__isnull=True)
            .select_related('product', 'product__category')
            .prefetch_related(
                Prefetch(
                    'product__images',
                    queryset=ProductImage.objects.order_by('-is_primary', 'sort_order', 'pk'),
                ),
                Prefetch(
                    'option_lines',
                    queryset=CL.objects.select_related('product').order_by('id'),
                ),
            )
            .annotate(
                line_total=ExpressionWrapper(
                    F('quantity') * Coalesce(F('product__list_price'), Value(Decimal('0'))),
                    output_field=money,
                )
            )
            .order_by('product__name')
        )
        # Compute per-line totals including options
        for ln in main_lines:
            opt_total = sum(
                (opt.option_price_delta if not opt.product_id else (opt.product.list_price or Decimal('0')))
                * opt.quantity
                for opt in ln.option_lines.all()
            )
            ln.line_total_with_options = ln.line_total + opt_total

        ctx['cart'] = cart
        ctx['lines'] = main_lines
        ctx['cart_total'] = sum((ln.line_total_with_options for ln in main_lines), Decimal('0'))
        ctx['cart_item_total'] = sum(ln.quantity for ln in main_lines)
        ctx['create_quote_form'] = CreateQuoteFromCartForm()
        ctx['create_order_form'] = CreateOrderFromCartForm()
        return ctx


class CartLineUpdateView(LoginRequiredMixin, View):
    def post(self, request, line_pk, *args, **kwargs):
        form = CartLineQuantityForm(request.POST)
        if form.is_valid():
            try:
                set_cart_line_quantity(
                    user=request.user,
                    line_id=line_pk,
                    quantity=form.cleaned_data['quantity'],
                    request=request,
                )
                messages.success(request, 'Cart updated.')
            except CartLine.DoesNotExist:
                messages.error(request, 'Cart line not found.')
        else:
            messages.error(request, 'Enter a valid quantity (0 or more).')
        return redirect('sales:cart')


class QuoteListView(LoginRequiredMixin, ListView):
    model = Quote
    template_name = 'sales/quote_list.html'
    context_object_name = 'quotes'
    paginate_by = 25

    def get_queryset(self):
        money = DecimalField(max_digits=14, decimal_places=2)
        qs = (
            Quote.objects.select_related('created_by', 'relation_organization')
            .annotate(
                line_count=Count('lines', distinct=True),
                lines_total=Coalesce(Sum('lines__line_total'), Value(Decimal('0')), output_field=money),
            )
        )
        g = self.request.GET
        qs = apply_relation_org_in(qs, g, field='relation_organization_id')
        qs = apply_status(qs, g, status_class=QuoteStatus)
        qs = apply_reference_icontains(qs, g)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(sales_list_filter_context(self.request, status_choices=QuoteStatus.choices))
        return ctx


class QuoteCreateFromCartView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        form = CreateQuoteFromCartForm(request.POST)
        if not form.is_valid():
            for errs in form.errors.values():
                for e in errs:
                    messages.error(request, e)
            return redirect('sales:cart')
        try:
            quote = create_quote_from_cart(
                user=request.user,
                relation_organization=form.cleaned_data['relation_organization'],
                internal_reference=form.cleaned_data.get('internal_reference') or '',
                external_reference=form.cleaned_data.get('external_reference') or '',
                request=request,
            )
            messages.success(request, f'Quote {quote.reference} created from your cart.')
            return redirect('sales:quote_detail', pk=quote.pk)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('sales:cart')


class OrderCreateFromCartView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        form = CreateOrderFromCartForm(request.POST)
        if not form.is_valid():
            for errs in form.errors.values():
                for e in errs:
                    messages.error(request, e)
            return redirect('sales:cart')
        try:
            order = create_order_from_cart(
                user=request.user,
                relation_organization=form.cleaned_data['relation_organization'],
                request=request,
            )
            messages.success(request, f'Order {order.reference} created from your cart.')
            return redirect('sales:order_detail', pk=order.pk)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('sales:cart')


class QuoteDetailView(LoginRequiredMixin, DetailView):
    model = Quote
    template_name = 'sales/quote_detail.html'
    context_object_name = 'quote'

    def get_queryset(self):
        from .models import QuoteLine as QL
        return Quote.objects.select_related('created_by', 'relation_organization').prefetch_related(
            Prefetch(
                'lines',
                queryset=QL.objects.filter(parent_line__isnull=True).select_related('product').prefetch_related(
                    Prefetch('option_lines', queryset=QL.objects.select_related('product').order_by('sort_order', 'id'))
                ),
                to_attr='main_lines',
            )
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q = self.object
        from django.utils import timezone
        ctx['today'] = timezone.localdate()
        ctx['main_lines'] = q.main_lines
        ctx['can_create_order'] = (
            not q.is_locked and not q.orders.exists() and bool(q.main_lines)
        )
        ctx['primary_order'] = q.orders.order_by('created_at').first()
        ctx['quote_total'] = q.lines.aggregate(s=Sum('line_total'))['s'] or Decimal('0')
        ctx['tax_breakdown'] = _tax_breakdown(q.main_lines)
        ctx['can_accept'] = q.status in (QuoteStatus.DRAFT, QuoteStatus.SENT) and not q.is_locked
        main_line_qs = q.lines.filter(parent_line__isnull=True)
        if q.is_locked:
            ctx['header_form'] = None
            ctx['formset'] = None
        else:
            ctx['header_form'] = QuoteHeaderForm(instance=q)
            ctx['formset'] = QuoteLineFormSet(instance=q, queryset=main_line_qs)
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.is_locked:
            messages.error(request, 'This quote is locked and cannot be edited.')
            return redirect(self.object)
        header_form = QuoteHeaderForm(request.POST, instance=self.object)
        main_line_qs = self.object.lines.filter(parent_line__isnull=True)
        formset = QuoteLineFormSet(request.POST, instance=self.object, queryset=main_line_qs)
        if header_form.is_valid() and formset.is_valid():
            header_form.save()
            formset.save()
            for line in self.object.lines.filter(parent_line__isnull=True):
                line.line_total = line.unit_price * line.quantity
                line.save(update_fields=['line_total'])
            log_event(
                action='quote.updated',
                entity_type='Quote',
                entity_id=self.object.id,
                request=request,
                metadata={'reference': self.object.reference},
            )
            messages.success(request, 'Quote saved.')
            return redirect(self.object)
        messages.error(request, 'Please correct the errors below.')
        context = self.get_context_data(object=self.object)
        context['header_form'] = header_form
        context['formset'] = formset
        return self.render_to_response(context)


class QuoteRefreshPricesView(LoginRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        quote = get_object_or_404(Quote, pk=pk)
        if quote.is_locked:
            messages.error(request, 'This quote is locked; prices cannot be refreshed.')
            return redirect('sales:quote_detail', pk=quote.pk)
        n = refresh_quote_prices_from_catalog(quote, request=request)
        messages.success(request, f'Refreshed prices on {n} line(s) from the catalog.')
        return redirect('sales:quote_detail', pk=quote.pk)


class QuoteCreateOrderView(LoginRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        quote = get_object_or_404(Quote, pk=pk)
        try:
            order = create_order_from_quote(quote=quote, user=request.user, request=request)
            messages.success(
                request,
                f'Order {order.reference} created. The quote is now locked.',
            )
            return redirect('sales:order_detail', pk=order.pk)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('sales:quote_detail', pk=quote.pk)


class QuoteAcceptView(LoginRequiredMixin, View):
    """Mark a quote as Accepted without creating an order (e.g. verbal/email acceptance)."""

    def post(self, request, pk, *args, **kwargs):
        quote = get_object_or_404(Quote, pk=pk)
        if quote.status not in (QuoteStatus.DRAFT, QuoteStatus.SENT):
            messages.error(request, f'Cannot accept a quote with status "{quote.get_status_display()}".')
            return redirect('sales:quote_detail', pk=quote.pk)
        quote.status = QuoteStatus.ACCEPTED
        quote.save(update_fields=['status', 'updated_at'])
        log_event(
            action='quote.accepted',
            entity_type='Quote',
            entity_id=quote.id,
            request=request,
            metadata={'reference': quote.reference},
        )
        messages.success(request, f'Quote {quote.reference} marked as accepted.')
        return redirect('sales:quote_detail', pk=quote.pk)


class SalesOrderListView(LoginRequiredMixin, ListView):
    model = SalesOrder
    template_name = 'sales/order_list.html'
    context_object_name = 'orders'
    paginate_by = 25

    def get_queryset(self):
        qs = SalesOrder.objects.select_related('created_by', 'quote', 'relation_organization')
        g = self.request.GET
        qs = apply_relation_org_in(qs, g, field='relation_organization_id')
        qs = apply_status(qs, g, status_class=OrderStatus)
        qs = apply_reference_icontains(qs, g)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(sales_list_filter_context(self.request, status_choices=OrderStatus.choices))
        return ctx


class SalesOrderDetailView(LoginRequiredMixin, DetailView):
    model = SalesOrder
    template_name = 'sales/order_detail.html'
    context_object_name = 'order'

    def get_queryset(self):
        from .models import OrderLine as OL
        return (
            SalesOrder.objects.select_related('created_by', 'quote', 'relation_organization')
            .prefetch_related(
                Prefetch(
                    'lines',
                    queryset=OL.objects.filter(parent_line__isnull=True).select_related('product').prefetch_related(
                        Prefetch('option_lines', queryset=OL.objects.select_related('product').order_by('sort_order', 'id'))
                    ),
                    to_attr='main_lines',
                ),
                'invoices',
                'fulfillment_orders',
                'shipping_orders',
            )
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        order = self.object
        open_invoice = (
            order.invoices.exclude(status=InvoiceStatus.CANCELLED).order_by('-created_at').first()
        )
        ctx['open_invoice'] = open_invoice
        if open_invoice:
            oi_total = open_invoice.total()
            oi_paid = open_invoice.amount_paid()
            ctx['open_invoice_balance'] = oi_total - oi_paid
            ctx['open_invoice_is_paid'] = ctx['open_invoice_balance'] <= Decimal('0')
        ctx['can_create_invoice'] = (
            open_invoice is None
            and order.lines.exists()
        )
        ctx['main_lines'] = order.main_lines
        ctx['order_total'] = order.lines.aggregate(s=Sum('line_total'))['s'] or Decimal('0')
        fulfillment = (
            order.fulfillment_orders.exclude(status=FulfillmentOrderStatus.CANCELLED)
            .order_by('-created_at')
            .first()
        )
        ctx['open_fulfillment'] = fulfillment
        ctx['can_create_fulfillment'] = (
            fulfillment is None
            and order.status != OrderStatus.CANCELLED
            and order.lines.exists()
        )
        ctx['shipping_orders'] = [
            sh
            for sh in order.shipping_orders.all()
            if sh.status != ShippingOrderStatus.CANCELLED
        ]
        return ctx


class SalesOrderStatusUpdateView(LoginRequiredMixin, View):
    """Confirm or cancel a sales order via a POST action."""

    _VALID_TRANSITIONS = {
        OrderStatus.DRAFT: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
        OrderStatus.CONFIRMED: {OrderStatus.CANCELLED},
    }

    def post(self, request, pk, *args, **kwargs):
        order = get_object_or_404(SalesOrder, pk=pk)
        action = request.POST.get('action', '')
        new_status_map = {'confirm': OrderStatus.CONFIRMED, 'cancel': OrderStatus.CANCELLED}
        new_status = new_status_map.get(action)
        if not new_status:
            messages.error(request, 'Unknown action.')
            return redirect(order)
        allowed = self._VALID_TRANSITIONS.get(order.status, set())
        if new_status not in allowed:
            messages.error(
                request,
                f'Cannot {action} an order that is already {order.get_status_display().lower()}.',
            )
            return redirect(order)
        old_status = order.status
        order.status = new_status
        order.save(update_fields=['status', 'updated_at'])
        log_event(
            action=f'order.{action}d',
            entity_type='SalesOrder',
            entity_id=order.id,
            request=request,
            metadata={'reference': order.reference, 'from': old_status, 'to': new_status},
        )
        labels = {OrderStatus.CONFIRMED: 'confirmed', OrderStatus.CANCELLED: 'cancelled'}
        messages.success(request, f'Order {order.reference} {labels[new_status]}.')
        return redirect(order)


class InvoiceCreateFromOrderView(LoginRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        order = get_object_or_404(SalesOrder, pk=pk)
        try:
            invoice = create_invoice_from_order(order=order, user=request.user, request=request)
            messages.success(request, f'Invoice {invoice.reference} created.')
            return redirect('sales:invoice_detail', pk=invoice.pk)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('sales:order_detail', pk=order.pk)


class FulfillmentCreateFromOrderView(LoginRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        order = get_object_or_404(SalesOrder, pk=pk)
        try:
            fo = create_fulfillment_order_from_sales_order(order=order, user=request.user, request=request)
            messages.success(
                request,
                f'Fulfillment order {fo.reference} created for the warehouse.',
            )
            return redirect('sales:fulfillment_detail', pk=fo.pk)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('sales:order_detail', pk=order.pk)


class FulfillmentOrderListView(LoginRequiredMixin, ListView):
    model = FulfillmentOrder
    template_name = 'sales/fulfillment_list.html'
    context_object_name = 'fulfillments'
    paginate_by = 25

    def get_queryset(self):
        qs = FulfillmentOrder.objects.select_related(
            'sales_order',
            'sales_order__relation_organization',
            'created_by',
        )
        g = self.request.GET
        qs = apply_relation_org_in(qs, g, field='sales_order__relation_organization_id')
        qs = apply_status(qs, g, status_class=FulfillmentOrderStatus)
        qs = apply_reference_icontains(qs, g)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            sales_list_filter_context(self.request, status_choices=FulfillmentOrderStatus.choices),
        )
        return ctx


class FulfillmentOrderDetailView(LoginRequiredMixin, DetailView):
    model = FulfillmentOrder
    template_name = 'sales/fulfillment_detail.html'
    context_object_name = 'fulfillment'

    def get_queryset(self):
        return FulfillmentOrder.objects.select_related('sales_order', 'created_by').prefetch_related(
            'lines__product',
            'shipping_orders',
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        fo = self.object
        lines = list(fo.lines.order_by('sort_order', 'id'))
        if fo.status == FulfillmentOrderStatus.CANCELLED:
            ctx['can_create_shipping'] = False
        else:
            ctx['can_create_shipping'] = any(fulfillment_line_unallocated_quantity(line) > 0 for line in lines)
        ctx['fulfillment_shipping_orders'] = [
            sh
            for sh in fo.shipping_orders.all()
            if sh.status != ShippingOrderStatus.CANCELLED
        ]
        ctx['line_remaining'] = [(line, fulfillment_line_unallocated_quantity(line)) for line in lines]
        return ctx


class FulfillmentOrderCompleteView(LoginRequiredMixin, View):
    """Mark a fulfillment order as Completed and decrement inventory stock."""

    def post(self, request, pk, *args, **kwargs):
        fo = get_object_or_404(FulfillmentOrder, pk=pk)
        if fo.status == FulfillmentOrderStatus.COMPLETED:
            messages.info(request, 'Already completed.')
            return redirect(fo)
        if fo.status == FulfillmentOrderStatus.CANCELLED:
            messages.error(request, 'Cannot complete a cancelled fulfillment order.')
            return redirect(fo)
        fo.status = FulfillmentOrderStatus.COMPLETED
        fo.save(update_fields=['status', 'updated_at'])
        # Decrement stock for each fulfillment line that has inventory-tracked products
        from inventory.services import decrement_stock_for_fulfillment
        decrement_stock_for_fulfillment(fo, request.user)
        log_event(
            action='fulfillment_order.completed',
            entity_type='FulfillmentOrder',
            entity_id=fo.id,
            request=request,
            metadata={'reference': fo.reference},
        )
        messages.success(request, f'Fulfillment order {fo.reference} marked as completed. Stock decremented.')
        return redirect(fo)


class ShippingOrderCreateFromFulfillmentView(LoginRequiredMixin, View):
    """Allocate quantities from a fulfillment order onto a new shipping order."""

    def dispatch(self, request, fulfillment_pk, *args, **kwargs):
        self.fulfillment = get_object_or_404(
            FulfillmentOrder.objects.prefetch_related('lines'),
            pk=fulfillment_pk,
        )
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, fulfillment_pk, *args, **kwargs):
        fo = self.fulfillment
        if fo.status == FulfillmentOrderStatus.CANCELLED:
            messages.error(request, 'Cancelled fulfillment orders cannot get new shipping orders.')
            return redirect(fo)
        if not any(fulfillment_line_unallocated_quantity(l) > 0 for l in fo.lines.all()):
            messages.error(request, 'Nothing left to allocate to a shipping order.')
            return redirect(fo)
        form_class = make_create_shipping_order_form(fo)
        return render(
            request,
            'sales/shipping_order_create.html',
            {'fulfillment': fo, 'form': form_class()},
        )

    def post(self, request, fulfillment_pk, *args, **kwargs):
        fo = self.fulfillment
        if fo.status == FulfillmentOrderStatus.CANCELLED:
            messages.error(request, 'Cancelled fulfillment orders cannot get new shipping orders.')
            return redirect(fo)
        form_class = make_create_shipping_order_form(fo)
        form = form_class(request.POST)
        if not form.is_valid():
            messages.error(request, 'Check the quantities and try again.')
            return render(request, 'sales/shipping_order_create.html', {'fulfillment': fo, 'form': form})
        quantities = {}
        for name, val in form.cleaned_data.items():
            if name.startswith('qty_'):
                pk_str = name[4:]
                quantities[pk_str] = int(val or 0)
        try:
            notes = form.cleaned_data.get('notes') or ''
            so = create_shipping_order_from_fulfillment(
                fulfillment_order=fo,
                user=request.user,
                quantities_by_line_id=quantities,
                notes=notes,
                request=request,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return render(request, 'sales/shipping_order_create.html', {'fulfillment': fo, 'form': form})
        messages.success(request, f'Shipping order {so.reference} created.')
        return redirect(so)


class ShippingOrderListView(LoginRequiredMixin, ListView):
    model = ShippingOrder
    template_name = 'sales/shipping_list.html'
    context_object_name = 'shipping_orders'
    paginate_by = 25

    def get_queryset(self):
        qs = ShippingOrder.objects.select_related(
            'sales_order',
            'sales_order__relation_organization',
            'fulfillment_order',
            'created_by',
        )
        g = self.request.GET
        qs = apply_relation_org_in(qs, g, field='sales_order__relation_organization_id')
        qs = apply_status(qs, g, status_class=ShippingOrderStatus)
        qs = apply_reference_icontains(qs, g)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            sales_list_filter_context(self.request, status_choices=ShippingOrderStatus.choices),
        )
        return ctx


class ShippingOrderDetailView(LoginRequiredMixin, DetailView):
    model = ShippingOrder
    template_name = 'sales/shipping_detail.html'
    context_object_name = 'shipping'

    def get_queryset(self):
        return ShippingOrder.objects.select_related(
            'fulfillment_order',
            'sales_order',
            'created_by',
        ).prefetch_related(
            'lines__fulfillment_line',
            'shipments__lines__shipping_order_line__fulfillment_line',
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sh = self.object
        ctx['header_form'] = ShipmentHeaderForm()
        ctx['lines_form'] = make_shipment_lines_form(sh)()
        line_rows = []
        any_unshipped = False
        for sol in sh.lines.select_related('fulfillment_line').order_by('id'):
            on_shipments = (
                sol.shipment_lines.exclude(shipment__status=ShipmentStatus.CANCELLED).aggregate(
                    s=Sum('quantity'),
                )['s']
                or 0
            )
            rem = sol.quantity - on_shipments
            if rem > 0:
                any_unshipped = True
            line_rows.append((sol, on_shipments, rem))
        ctx['shipping_line_rows'] = line_rows
        ctx['can_add_shipment'] = (
            sh.status != ShippingOrderStatus.CANCELLED and sh.lines.exists() and any_unshipped
        )
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        sh = self.object
        if sh.status == ShippingOrderStatus.CANCELLED:
            messages.error(request, 'Cannot add shipments to a cancelled shipping order.')
            return redirect(sh)
        header_form = ShipmentHeaderForm(request.POST)
        lines_form_class = make_shipment_lines_form(sh)
        lines_form = lines_form_class(request.POST)
        if header_form.is_valid() and lines_form.is_valid():
            quantities = {}
            for name, val in lines_form.cleaned_data.items():
                if name.startswith('qty_'):
                    quantities[name[4:]] = int(val or 0)
            try:
                create_shipment_for_shipping_order(
                    shipping_order=sh,
                    user=request.user,
                    carrier=header_form.cleaned_data.get('carrier') or '',
                    tracking_number=header_form.cleaned_data.get('tracking_number') or '',
                    notes=header_form.cleaned_data.get('notes') or '',
                    lines_qty=quantities,
                    request=request,
                )
            except ValueError as exc:
                messages.error(request, str(exc))
                ctx = self.get_context_data(object=sh)
                ctx['header_form'] = header_form
                ctx['lines_form'] = lines_form
                return self.render_to_response(ctx)
            messages.success(request, 'Shipment added.')
            return redirect(sh)
        messages.error(request, 'Correct the form errors below.')
        ctx = self.get_context_data(object=sh)
        ctx['header_form'] = header_form
        ctx['lines_form'] = lines_form
        return self.render_to_response(ctx)


class InvoiceListView(LoginRequiredMixin, ListView):
    model = Invoice
    template_name = 'sales/invoice_list.html'
    context_object_name = 'invoices'
    paginate_by = 25

    def get_queryset(self):
        money = DecimalField(max_digits=14, decimal_places=2)
        qs = (
            Invoice.objects.select_related('order', 'relation_organization', 'created_by')
            .annotate(
                inv_total=Coalesce(Sum('lines__line_total'), Value(Decimal('0')), output_field=money),
                inv_paid=Coalesce(Sum('payments__amount'), Value(Decimal('0')), output_field=money),
            )
            .annotate(
                inv_balance=ExpressionWrapper(F('inv_total') - F('inv_paid'), output_field=money),
            )
        )
        g = self.request.GET
        qs = apply_relation_org_in(qs, g, field='relation_organization_id')
        qs = apply_status(qs, g, status_class=InvoiceStatus)
        qs = apply_reference_icontains(qs, g)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(sales_list_filter_context(self.request, status_choices=InvoiceStatus.choices))
        return ctx


class InvoiceDetailView(LoginRequiredMixin, DetailView):
    model = Invoice
    template_name = 'sales/invoice_detail.html'
    context_object_name = 'invoice'

    def get_queryset(self):
        from .models import InvoiceLine as IL
        return (
            Invoice.objects.select_related('order', 'relation_organization', 'created_by')
            .prefetch_related(
                Prefetch(
                    'lines',
                    queryset=IL.objects.filter(parent_line__isnull=True).select_related('product').prefetch_related(
                        Prefetch('option_lines', queryset=IL.objects.select_related('product').order_by('sort_order', 'id'))
                    ),
                    to_attr='main_lines',
                ),
                'payments__created_by',
            )
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        inv = self.object
        ctx['main_lines'] = inv.main_lines
        inv_total = inv.total()
        inv_paid = inv.amount_paid()
        inv_balance = inv_total - inv_paid
        inv_is_paid = inv_balance <= Decimal('0')
        ctx['invoice_total'] = inv_total
        ctx['invoice_paid'] = inv_paid
        ctx['invoice_balance'] = inv_balance
        ctx['invoice_is_paid'] = inv_is_paid
        ctx['tax_breakdown'] = _tax_breakdown(inv.main_lines)
        ctx['payment_form'] = InvoicePaymentForm(max_amount=inv_balance if not inv_is_paid else None)
        ctx['can_record_payment'] = inv.status != InvoiceStatus.CANCELLED and not inv_is_paid
        ctx['credit_notes'] = inv.credit_notes.order_by('created_at')
        ctx['credit_notes_total'] = sum(cn.total() for cn in ctx['credit_notes'])
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        inv = self.object
        inv_total = inv.total()
        inv_paid = inv.amount_paid()
        if inv.status == InvoiceStatus.CANCELLED or inv_total - inv_paid <= Decimal('0'):
            messages.error(request, 'No further payments can be recorded for this invoice.')
            return redirect(inv)
        form = InvoicePaymentForm(request.POST)
        if form.is_valid():
            try:
                add_invoice_payment(
                    invoice=inv,
                    amount=form.cleaned_data['amount'],
                    reference_note=form.cleaned_data.get('reference_note') or '',
                    user=request.user,
                    request=request,
                )
                new_balance = inv.balance_due()
                if new_balance <= Decimal('0'):
                    messages.success(request, 'Payment recorded. Invoice is paid in full.')
                else:
                    messages.success(
                        request,
                        f'Payment recorded. Balance due: {new_balance} {inv.currency}.',
                    )
            except ValueError as exc:
                messages.error(request, str(exc))
        else:
            messages.error(request, 'Correct the payment form errors.')
            ctx = self.get_context_data(object=inv)
            ctx['payment_form'] = form
            return self.render_to_response(ctx)
        return redirect(inv)


class InvoiceCancelView(LoginRequiredMixin, View):
    """Cancel an issued invoice (no payments must exceed zero)."""

    def post(self, request, pk):
        inv = get_object_or_404(Invoice, pk=pk)
        if inv.status == InvoiceStatus.CANCELLED:
            messages.info(request, 'Invoice is already cancelled.')
            return redirect(inv)
        inv.status = InvoiceStatus.CANCELLED
        inv.save(update_fields=['status', 'updated_at'])
        log_event(
            action='invoice.cancelled',
            entity_type='Invoice',
            entity_id=inv.id,
            request=request,
            metadata={'reference': inv.reference},
        )
        messages.success(request, f'Invoice {inv.reference} cancelled.')
        return redirect(inv)


class InvoiceDueDateView(LoginRequiredMixin, View):
    """Set or update the due date on an invoice."""

    def post(self, request, pk):
        inv = get_object_or_404(Invoice, pk=pk)
        due_date_str = request.POST.get('due_date', '').strip()
        if not due_date_str:
            messages.error(request, 'Please enter a valid date.')
            return redirect(inv)
        from datetime import date
        try:
            due = date.fromisoformat(due_date_str)
        except ValueError:
            messages.error(request, 'Invalid date format. Use YYYY-MM-DD.')
            return redirect(inv)
        inv.due_date = due
        inv.save(update_fields=['due_date', 'updated_at'])
        messages.success(request, f'Due date set to {due}.')
        return redirect(inv)


class QuoteMarkExpiredView(LoginRequiredMixin, View):
    """Manually mark a quote as expired."""

    def post(self, request, pk):
        from .models import Quote, QuoteStatus
        quote = get_object_or_404(Quote, pk=pk)
        if quote.status not in (QuoteStatus.DRAFT, QuoteStatus.SENT):
            messages.error(request, 'Only draft or sent quotes can be marked expired.')
            return redirect(quote)
        quote.status = QuoteStatus.EXPIRED
        quote.save(update_fields=['status', 'updated_at'])
        log_event(
            action='quote.expired',
            entity_type='Quote',
            entity_id=quote.id,
            request=request,
            metadata={'reference': quote.reference},
        )
        messages.success(request, f'Quote {quote.reference} marked as expired.')
        return redirect(quote)


class ShipmentStatusUpdateView(LoginRequiredMixin, View):
    """Update the status of a single Shipment (parcel) within a shipping order."""

    _VALID_TRANSITIONS = {
        'planned': {'in_transit', 'cancelled'},
        'in_transit': {'delivered', 'cancelled'},
    }

    def post(self, request, shipping_pk, shipment_pk):
        from .models import Shipment, ShipmentStatus
        shipping = get_object_or_404(ShippingOrder, pk=shipping_pk)
        shipment = get_object_or_404(Shipment, pk=shipment_pk, shipping_order=shipping)
        new_status = request.POST.get('status', '')
        allowed = self._VALID_TRANSITIONS.get(shipment.status, set())
        if new_status not in allowed:
            messages.error(request, f'Cannot transition from {shipment.get_status_display()} to {new_status}.')
            return redirect(shipping)
        from django.utils import timezone as tz
        shipment.status = new_status
        if new_status == 'in_transit':
            shipment.shipped_at = tz.now()
        shipment.save(update_fields=['status', 'shipped_at', 'updated_at'])
        messages.success(request, f'Shipment #{shipment.sequence} marked as {shipment.get_status_display()}.')
        return redirect(shipping)


class InvoiceCsvExportView(LoginRequiredMixin, View):
    """Download all issued invoices as a flat CSV."""

    def get(self, request, *args, **kwargs):
        money = DecimalField(max_digits=14, decimal_places=2)
        qs = (
            Invoice.objects
            .filter(status=InvoiceStatus.ISSUED)
            .select_related('relation_organization', 'order')
            .annotate(
                inv_total=Coalesce(Sum('lines__line_total'), Value(Decimal('0')), output_field=money),
                inv_paid=Coalesce(Sum('payments__amount'), Value(Decimal('0')), output_field=money),
            )
            .annotate(balance=ExpressionWrapper(F('inv_total') - F('inv_paid'), output_field=money))
            .order_by('-created_at')
        )

        def stream():
            import io
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(['Reference', 'Date', 'Due date', 'Customer', 'Order', 'Currency', 'Total', 'Paid', 'Balance'])
            yield buf.getvalue(); buf.seek(0); buf.truncate()
            for inv in qs:
                w.writerow([
                    inv.reference,
                    inv.created_at.date(),
                    inv.due_date or '',
                    inv.relation_organization.name if inv.relation_organization_id else '',
                    inv.order.reference,
                    inv.currency,
                    str(inv.inv_total),
                    str(inv.inv_paid),
                    str(inv.balance),
                ])
                yield buf.getvalue(); buf.seek(0); buf.truncate()

        response = StreamingHttpResponse(stream(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="invoices.csv"'
        return response


class QuotePrintView(LoginRequiredMixin, DetailView):
    model = Quote
    template_name = 'sales/quote_print.html'
    context_object_name = 'quote'

    def get_queryset(self):
        from .models import QuoteLine as QL
        return Quote.objects.select_related('created_by', 'relation_organization').prefetch_related(
            'lines__product',
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q = self.object
        main_lines = list(q.lines.filter(parent_line__isnull=True).select_related('product').prefetch_related('option_lines'))
        ctx['main_lines'] = main_lines
        ctx['quote_total'] = q.lines.aggregate(s=Sum('line_total'))['s'] or Decimal('0')
        ctx['tax_breakdown'] = _tax_breakdown(main_lines)
        tax_total = sum(row['tax'] for row in ctx['tax_breakdown'])
        ctx['tax_total'] = tax_total
        ctx['grand_total'] = ctx['quote_total'] + tax_total
        return ctx


class InvoicePrintView(LoginRequiredMixin, DetailView):
    model = Invoice
    template_name = 'sales/invoice_print.html'
    context_object_name = 'invoice'

    def get_queryset(self):
        from .models import InvoiceLine as IL
        return Invoice.objects.select_related('order', 'relation_organization', 'created_by').prefetch_related(
            'lines__product',
            'payments',
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        inv = self.object
        main_lines = list(inv.lines.filter(parent_line__isnull=True).select_related('product').prefetch_related('option_lines'))
        ctx['main_lines'] = main_lines
        ctx['invoice_total'] = inv.total()
        ctx['invoice_paid'] = inv.amount_paid()
        ctx['invoice_balance'] = inv.total() - inv.amount_paid()
        ctx['invoice_is_paid'] = ctx['invoice_balance'] <= Decimal('0')
        ctx['tax_breakdown'] = _tax_breakdown(main_lines)
        tax_total = sum(row['tax'] for row in ctx['tax_breakdown'])
        ctx['tax_total'] = tax_total
        ctx['grand_total'] = ctx['invoice_total'] + tax_total
        return ctx


# ── Credit notes ──────────────────────────────────────────────────────────────

class CreditNoteListView(LoginRequiredMixin, ListView):
    template_name = 'sales/credit_note_list.html'
    context_object_name = 'credit_notes'
    paginate_by = 50

    def get_queryset(self):
        return CreditNote.objects.select_related('invoice', 'relation_organization').order_by('-created_at')


class CreditNoteDetailView(LoginRequiredMixin, DetailView):
    model = CreditNote
    template_name = 'sales/credit_note_detail.html'
    context_object_name = 'credit_note'

    def get_queryset(self):
        return CreditNote.objects.select_related('invoice', 'relation_organization', 'created_by').prefetch_related('lines')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        cn = self.object
        ctx['main_lines'] = list(cn.lines.order_by('sort_order', 'id'))
        ctx['cn_total'] = cn.total()
        ctx['tax_breakdown'] = _tax_breakdown(ctx['main_lines'])
        ctx['tax_total'] = sum(row['tax'] for row in ctx['tax_breakdown'])
        ctx['grand_total'] = ctx['cn_total'] + ctx['tax_total']
        return ctx


class CreditNoteCreateView(LoginRequiredMixin, View):
    """Create a credit note against an invoice. Pre-populates lines from the invoice."""

    template_name = 'sales/credit_note_form.html'

    def _get_invoice(self, pk):
        return get_object_or_404(
            Invoice.objects.select_related('relation_organization').prefetch_related('lines'),
            pk=pk,
        )

    def get(self, request, invoice_pk):
        invoice = self._get_invoice(invoice_pk)
        main_lines = list(invoice.lines.filter(parent_line__isnull=True).order_by('sort_order', 'id'))
        return render(request, self.template_name, {
            'invoice': invoice,
            'main_lines': main_lines,
        })

    def post(self, request, invoice_pk):
        from django.db import transaction as db_transaction

        invoice = self._get_invoice(invoice_pk)
        reason = request.POST.get('reason', '').strip()
        notes = request.POST.get('notes', '').strip()

        # Collect submitted line data
        main_lines = list(invoice.lines.filter(parent_line__isnull=True).order_by('sort_order', 'id'))
        selected_lines = []
        for i, line in enumerate(main_lines):
            qty_str = request.POST.get(f'qty_{line.pk}', '').strip()
            if not qty_str:
                continue
            try:
                qty = int(qty_str)
            except ValueError:
                continue
            if qty <= 0:
                continue
            qty = min(qty, line.quantity)
            selected_lines.append((line, qty))

        if not selected_lines:
            messages.error(request, 'Select at least one line with a quantity greater than zero.')
            return render(request, self.template_name, {
                'invoice': invoice,
                'main_lines': main_lines,
                'posted': request.POST,
            })

        with db_transaction.atomic():
            cn = CreditNote.objects.create(
                reference=next_credit_note_reference(),
                invoice=invoice,
                created_by=request.user,
                relation_organization=invoice.relation_organization,
                currency=invoice.currency,
                reason=reason,
                notes=notes,
            )
            for sort_order, (inv_line, qty) in enumerate(selected_lines):
                CreditNoteLine.objects.create(
                    credit_note=cn,
                    invoice_line=inv_line,
                    product_name=inv_line.product_name,
                    sku=inv_line.sku,
                    quantity=qty,
                    unit_price=inv_line.unit_price,
                    tax_rate_pct=inv_line.tax_rate_pct,
                    currency=inv_line.currency,
                    line_total=inv_line.unit_price * qty,
                    sort_order=sort_order,
                )

        log_event(
            actor=request.user,
            verb='created',
            target=cn,
            detail=f'Credit note {cn.reference} issued against invoice {invoice.reference}.',
            request=request,
        )
        messages.success(request, f'Credit note {cn.reference} created.')
        return redirect(cn)


class CreditNotePrintView(LoginRequiredMixin, DetailView):
    model = CreditNote
    template_name = 'sales/credit_note_print.html'
    context_object_name = 'credit_note'

    def get_queryset(self):
        return CreditNote.objects.select_related('invoice', 'relation_organization', 'created_by').prefetch_related('lines')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        cn = self.object
        ctx['main_lines'] = list(cn.lines.order_by('sort_order', 'id'))
        ctx['cn_total'] = cn.total()
        ctx['tax_breakdown'] = _tax_breakdown(ctx['main_lines'])
        ctx['tax_total'] = sum(row['tax'] for row in ctx['tax_breakdown'])
        ctx['grand_total'] = ctx['cn_total'] + ctx['tax_total']
        return ctx
