"""
Report views — read-only aggregated data pages.
All views require login; most require staff status.
"""
from __future__ import annotations

import csv
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth
from django.http import StreamingHttpResponse
from django.utils import timezone
from django.views.generic import TemplateView


MONEY = DecimalField(max_digits=14, decimal_places=2)


class SalesReportView(LoginRequiredMixin, TemplateView):
    template_name = 'core/reports/sales_report.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from sales.models import Invoice, InvoiceStatus, InvoiceLine

        # Monthly revenue (last 12 months)
        today_date = timezone.localdate()
        month = today_date.month - 11
        year = today_date.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        twelve_ago = today_date.replace(year=year, month=month, day=1)

        monthly = (
            Invoice.objects
            .filter(status=InvoiceStatus.ISSUED)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(revenue=Coalesce(Sum('lines__line_total'), Value(Decimal('0')), output_field=MONEY))
            .order_by('month')
        )
        ctx['monthly_revenue'] = list(monthly)

        # Top 10 products by revenue
        top_products = (
            InvoiceLine.objects
            .filter(invoice__status=InvoiceStatus.ISSUED, parent_line__isnull=True)
            .values('sku', 'product_name')
            .annotate(total=Coalesce(Sum('line_total'), Value(Decimal('0')), output_field=MONEY))
            .order_by('-total')[:10]
        )
        ctx['top_products'] = list(top_products)

        # Top 10 customers by revenue
        from relations.models import Organization
        top_customers = (
            Invoice.objects
            .filter(status=InvoiceStatus.ISSUED, relation_organization__isnull=False)
            .values('relation_organization__name')
            .annotate(total=Coalesce(Sum('lines__line_total'), Value(Decimal('0')), output_field=MONEY))
            .order_by('-total')[:10]
        )
        ctx['top_customers'] = list(top_customers)

        ctx['today'] = timezone.localdate()
        return ctx


class AgedDebtorsReportView(LoginRequiredMixin, TemplateView):
    template_name = 'core/reports/aged_debtors.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from sales.models import Invoice, InvoiceStatus

        today = timezone.localdate()

        unpaid_qs = (
            Invoice.objects
            .filter(status=InvoiceStatus.ISSUED)
            .select_related('relation_organization', 'order')
            .annotate(
                inv_total=Coalesce(Sum('lines__line_total'), Value(Decimal('0')), output_field=MONEY),
                inv_paid=Coalesce(Sum('payments__amount'), Value(Decimal('0')), output_field=MONEY),
            )
            .annotate(
                balance=ExpressionWrapper(F('inv_total') - F('inv_paid'), output_field=MONEY),
            )
            .filter(balance__gt=0)
            .order_by('due_date', 'created_at')
        )

        buckets = {'current': [], '1_30': [], '31_60': [], '61_90': [], 'over_90': []}
        totals = {k: Decimal('0') for k in buckets}

        for inv in unpaid_qs:
            if inv.due_date is None:
                age = 0
            else:
                age = (today - inv.due_date).days

            if age <= 0:
                key = 'current'
            elif age <= 30:
                key = '1_30'
            elif age <= 60:
                key = '31_60'
            elif age <= 90:
                key = '61_90'
            else:
                key = 'over_90'

            inv.age_days = age
            buckets[key].append(inv)
            totals[key] += inv.balance

        ctx['buckets'] = buckets
        ctx['totals'] = totals
        ctx['grand_total'] = sum(totals.values())
        ctx['today'] = today
        return ctx


class InventoryValuationReportView(LoginRequiredMixin, TemplateView):
    template_name = 'core/reports/inventory_valuation.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from inventory.models import StockEntry
        from catalog.models import Product

        entries = (
            StockEntry.objects
            .filter(quantity_on_hand__gt=0)
            .select_related('product__category', 'location__warehouse')
            .order_by('product__category__name', 'product__name', 'location__warehouse__name')
        )

        rows = []
        total_cost = Decimal('0')
        total_retail = Decimal('0')
        for e in entries:
            p = e.product
            cost = (p.purchase_price or Decimal('0')) * e.quantity_on_hand
            retail = (p.list_price or Decimal('0')) * e.quantity_on_hand
            rows.append({
                'product': p,
                'location': e.location,
                'qty': e.quantity_on_hand,
                'purchase_price': p.purchase_price,
                'list_price': p.list_price,
                'cost_value': cost,
                'retail_value': retail,
            })
            total_cost += cost
            total_retail += retail

        ctx['rows'] = rows
        ctx['total_cost'] = total_cost
        ctx['total_retail'] = total_retail
        ctx['today'] = timezone.localdate()
        return ctx


class InventoryValuationCsvView(LoginRequiredMixin, TemplateView):
    """Download inventory valuation as CSV."""

    def get(self, request, *args, **kwargs):
        from inventory.models import StockEntry

        entries = (
            StockEntry.objects
            .filter(quantity_on_hand__gt=0)
            .select_related('product__category', 'location__warehouse')
            .order_by('product__category__name', 'product__name')
        )

        def stream():
            import io
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(['SKU', 'Product', 'Category', 'Warehouse', 'Location', 'Qty', 'Purchase price', 'Cost value', 'List price', 'Retail value'])
            yield buf.getvalue(); buf.seek(0); buf.truncate()
            for e in entries:
                p = e.product
                cost = (p.purchase_price or Decimal('0')) * e.quantity_on_hand
                retail = (p.list_price or Decimal('0')) * e.quantity_on_hand
                w.writerow([p.sku, p.name, p.category.name, e.location.warehouse.name, e.location.code, str(e.quantity_on_hand), str(p.purchase_price or ''), str(cost), str(p.list_price or ''), str(retail)])
                yield buf.getvalue(); buf.seek(0); buf.truncate()

        response = StreamingHttpResponse(stream(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="inventory_valuation.csv"'
        return response


class SalesReportCsvView(LoginRequiredMixin, TemplateView):
    """Download invoice lines as CSV."""

    def get(self, request, *args, **kwargs):
        from sales.models import Invoice, InvoiceStatus, InvoiceLine

        lines = (
            InvoiceLine.objects
            .filter(invoice__status=InvoiceStatus.ISSUED, parent_line__isnull=True)
            .select_related('invoice__relation_organization', 'invoice__order')
            .order_by('invoice__created_at')
        )

        def stream():
            import io
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(['Invoice', 'Date', 'Customer', 'SKU', 'Product', 'Qty', 'Unit price', 'Tax %', 'Line total', 'Currency'])
            yield buf.getvalue(); buf.seek(0); buf.truncate()
            for ln in lines:
                inv = ln.invoice
                w.writerow([
                    inv.reference,
                    inv.created_at.date(),
                    inv.relation_organization.name if inv.relation_organization_id else '',
                    ln.sku, ln.product_name, ln.quantity,
                    str(ln.unit_price), str(ln.tax_rate_pct or ''),
                    str(ln.line_total), ln.currency,
                ])
                yield buf.getvalue(); buf.seek(0); buf.truncate()

        response = StreamingHttpResponse(stream(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="sales_report.csv"'
        return response
