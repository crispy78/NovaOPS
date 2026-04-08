from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.views.generic import TemplateView


class GlobalSearchView(LoginRequiredMixin, TemplateView):
    template_name = 'core/search.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q = (self.request.GET.get('q') or '').strip()
        ctx['q'] = q

        if not q:
            return ctx

        from catalog.models import Product
        from relations.models import Organization, Person
        from sales.models import Quote, SalesOrder, Invoice

        ctx['products'] = (
            Product.objects.filter(
                is_archived=False
            ).filter(
                Q(name__icontains=q) | Q(sku__icontains=q) | Q(mpn__icontains=q) | Q(brand__icontains=q)
            ).select_related('category')[:10]
        )

        ctx['organizations'] = (
            Organization.objects.filter(is_archived=False).filter(
                Q(name__icontains=q) | Q(registration_number__icontains=q) | Q(tax_id_vat__icontains=q)
            )[:10]
        )

        ctx['people'] = (
            Person.objects.filter(is_archived=False).filter(
                Q(first_name__icontains=q) | Q(last_name__icontains=q)
            )[:10]
        )

        ctx['quotes'] = (
            Quote.objects.filter(
                Q(reference__icontains=q) | Q(internal_reference__icontains=q) | Q(external_reference__icontains=q)
            ).select_related('relation_organization')[:10]
        )

        ctx['orders'] = (
            SalesOrder.objects.filter(reference__icontains=q)
            .select_related('relation_organization')[:10]
        )

        ctx['invoices'] = (
            Invoice.objects.filter(reference__icontains=q)
            .select_related('relation_organization')[:10]
        )

        return ctx
