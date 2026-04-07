from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Sum
from django.views.generic import DetailView, ListView

from .models import StockEntry, StockLocation, Warehouse


class WarehouseListView(LoginRequiredMixin, ListView):
    model = Warehouse
    template_name = 'inventory/warehouse_list.html'
    context_object_name = 'warehouses'

    def get_queryset(self):
        return Warehouse.objects.prefetch_related('locations')


class WarehouseDetailView(LoginRequiredMixin, DetailView):
    model = Warehouse
    template_name = 'inventory/warehouse_detail.html'
    context_object_name = 'warehouse'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        warehouse = ctx['warehouse']
        locations = StockLocation.objects.filter(warehouse=warehouse).prefetch_related(
            'stock_entries__product',
        )
        ctx['locations'] = locations
        ctx['total_skus'] = (
            StockEntry.objects.filter(location__warehouse=warehouse, quantity_on_hand__gt=0)
            .values('product').distinct().count()
        )
        return ctx
