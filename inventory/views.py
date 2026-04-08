from __future__ import annotations

from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.views import View
from django.views.generic import DetailView, ListView

from catalog.models import Product

from .models import MovementType, StockEntry, StockLocation, StockMovement, Warehouse
from .services import adjust_stock


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


class StockAdjustForm(forms.Form):
    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_archived=False, inventory_tracked=True).order_by('name'),
        label='Product',
    )
    location = forms.ModelChoiceField(
        queryset=StockLocation.objects.filter(is_active=True).select_related('warehouse').order_by('warehouse__name', 'code'),
        label='Location',
    )
    delta = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        label='Quantity change',
        help_text='Use a positive number to add stock, negative to remove.',
    )
    notes = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
        label='Notes / reason',
    )

    def clean_delta(self):
        delta = self.cleaned_data['delta']
        if delta == 0:
            raise forms.ValidationError('Delta must be non-zero.')
        return delta


class StockAdjustView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'inventory.change_stockentry'
    template_name = 'inventory/stock_adjust.html'

    def get(self, request):
        form = StockAdjustForm()
        # Pre-fill product/location from query params (convenience when navigating from product page)
        product_pk = request.GET.get('product')
        location_pk = request.GET.get('location')
        if product_pk or location_pk:
            initial = {}
            if product_pk:
                initial['product'] = product_pk
            if location_pk:
                initial['location'] = location_pk
            form = StockAdjustForm(initial=initial)
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = StockAdjustForm(request.POST)
        if form.is_valid():
            entry = adjust_stock(
                product=form.cleaned_data['product'],
                location=form.cleaned_data['location'],
                delta=form.cleaned_data['delta'],
                notes=form.cleaned_data.get('notes', ''),
                user=request.user,
            )
            delta = form.cleaned_data['delta']
            sign = '+' if delta > 0 else ''
            messages.success(
                request,
                f'Stock adjusted: {entry.product.sku} @ {entry.location} '
                f'({sign}{delta:f}) → {entry.quantity_on_hand:f} on hand.',
            )
            return redirect('inventory:stock_adjust')
        return render(request, self.template_name, {'form': form})


class LowStockListView(LoginRequiredMixin, ListView):
    """Products whose total stock on hand is at or below their reorder point."""

    template_name = 'inventory/low_stock.html'
    context_object_name = 'low_stock_items'

    def get_queryset(self):
        from django.db.models import DecimalField, F, OuterRef, Subquery
        from django.db.models.functions import Coalesce

        total_qs = (
            StockEntry.objects
            .filter(product=OuterRef('pk'))
            .values('product')
            .annotate(total=Sum('quantity_on_hand'))
            .values('total')
        )
        money = DecimalField(max_digits=14, decimal_places=3)
        return (
            Product.objects
            .filter(is_archived=False, inventory_tracked=True, reorder_point__isnull=False)
            .annotate(
                total_on_hand=Coalesce(Subquery(total_qs, output_field=money), Decimal('0'), output_field=money)
            )
            .filter(total_on_hand__lte=F('reorder_point'))
            .select_related('category')
            .order_by('name')
        )


class StockTransferForm(forms.Form):
    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_archived=False, inventory_tracked=True).order_by('name'),
        label='Product',
    )
    from_location = forms.ModelChoiceField(
        queryset=StockLocation.objects.filter(is_active=True).select_related('warehouse').order_by('warehouse__name', 'code'),
        label='From location',
    )
    to_location = forms.ModelChoiceField(
        queryset=StockLocation.objects.filter(is_active=True).select_related('warehouse').order_by('warehouse__name', 'code'),
        label='To location',
    )
    quantity = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal('0.001'),
        label='Quantity to transfer',
    )
    notes = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
        label='Notes / reason',
    )

    def clean(self):
        cleaned = super().clean()
        src = cleaned.get('from_location')
        dst = cleaned.get('to_location')
        if src and dst and src == dst:
            raise forms.ValidationError('Source and destination locations must be different.')
        return cleaned


class StockTransferView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'inventory.change_stockentry'
    template_name = 'inventory/stock_transfer.html'

    def get(self, request):
        return render(request, self.template_name, {'form': StockTransferForm()})

    def post(self, request):
        from django.db import transaction as db_tx
        form = StockTransferForm(request.POST)
        if form.is_valid():
            product = form.cleaned_data['product']
            src_loc = form.cleaned_data['from_location']
            dst_loc = form.cleaned_data['to_location']
            qty = form.cleaned_data['quantity']
            notes = form.cleaned_data.get('notes', '')

            with db_tx.atomic():
                src_entry = (
                    StockEntry.objects
                    .select_for_update()
                    .filter(product=product, location=src_loc)
                    .first()
                )
                if not src_entry or src_entry.quantity_on_hand < qty:
                    available = src_entry.quantity_on_hand if src_entry else Decimal('0')
                    form.add_error('quantity', f'Insufficient stock at {src_loc}: {available:f} available.')
                    return render(request, self.template_name, {'form': form})

                src_entry.quantity_on_hand -= qty
                src_entry.save(update_fields=['quantity_on_hand', 'last_updated'])

                dst_entry, _ = StockEntry.objects.select_for_update().get_or_create(
                    product=product,
                    location=dst_loc,
                    defaults={'quantity_on_hand': Decimal('0')},
                )
                dst_entry.quantity_on_hand += qty
                dst_entry.save(update_fields=['quantity_on_hand', 'last_updated'])

                ref = f'TRANSFER {src_loc} → {dst_loc}'
                StockMovement.objects.create(
                    product=product, location=src_loc,
                    delta=-qty, movement_type=MovementType.TRANSFER,
                    reference=ref, notes=notes, created_by=request.user,
                )
                StockMovement.objects.create(
                    product=product, location=dst_loc,
                    delta=qty, movement_type=MovementType.TRANSFER,
                    reference=ref, notes=notes, created_by=request.user,
                )

            messages.success(
                request,
                f'Transferred {qty:f} × {product.sku} from {src_loc} to {dst_loc}.',
            )
            return redirect('inventory:stock_transfer')
        return render(request, self.template_name, {'form': form})
