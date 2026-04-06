from __future__ import annotations

import mimetypes
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse, Http404
from django.utils import timezone
from django.utils._os import safe_join
from django.views.generic import TemplateView


@login_required
def protected_media(request, path: str):
    """
    Serve MEDIA files behind authentication in development.

    Production deployments should serve media via the reverse proxy/web server,
    ideally with auth/authorization (or signed URLs) depending on sensitivity.
    """
    try:
        full_path = safe_join(str(settings.MEDIA_ROOT), path)
    except Exception as exc:
        raise Http404() from exc

    p = Path(full_path)
    if not p.exists() or not p.is_file():
        raise Http404()

    content_type, _ = mimetypes.guess_type(str(p))
    return FileResponse(open(p, 'rb'), content_type=content_type or 'application/octet-stream')


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'core/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from sales.models import (
            Invoice,
            InvoiceStatus,
            OrderStatus,
            Quote,
            QuoteStatus,
            SalesOrder,
        )

        today = timezone.localdate()
        money = DecimalField(max_digits=14, decimal_places=2)

        # ── Quick stats ──────────────────────────────────────────────────────
        ctx['open_orders_count'] = SalesOrder.objects.filter(
            status__in=[OrderStatus.DRAFT, OrderStatus.CONFIRMED]
        ).count()

        ctx['active_quotes_count'] = Quote.objects.filter(
            status__in=[QuoteStatus.DRAFT, QuoteStatus.SENT]
        ).count()

        ctx['expiring_quotes_count'] = Quote.objects.filter(
            status__in=[QuoteStatus.DRAFT, QuoteStatus.SENT],
            valid_until__lt=today,
            valid_until__isnull=False,
        ).count()

        unpaid_qs = (
            Invoice.objects.filter(status=InvoiceStatus.ISSUED)
            .annotate(
                inv_total=Coalesce(Sum('lines__line_total'), Value(Decimal('0')), output_field=money),
                inv_paid=Coalesce(Sum('payments__amount'), Value(Decimal('0')), output_field=money),
            )
            .annotate(
                inv_balance=ExpressionWrapper(F('inv_total') - F('inv_paid'), output_field=money),
            )
            .filter(inv_balance__gt=0)
        )
        ctx['unpaid_invoices_count'] = unpaid_qs.count()

        # ── Recent items ─────────────────────────────────────────────────────
        ctx['recent_quotes'] = (
            Quote.objects.filter(status__in=[QuoteStatus.DRAFT, QuoteStatus.SENT])
            .select_related('relation_organization')
            .order_by('-created_at')[:5]
        )

        ctx['recent_orders'] = (
            SalesOrder.objects.filter(status__in=[OrderStatus.DRAFT, OrderStatus.CONFIRMED])
            .select_related('relation_organization')
            .order_by('-created_at')[:5]
        )

        ctx['recent_unpaid_invoices'] = (
            unpaid_qs.select_related('order', 'relation_organization').order_by('-created_at')[:5]
        )

        ctx['today'] = today
        return ctx

