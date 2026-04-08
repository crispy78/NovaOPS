from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView
from django.views.generic.edit import CreateView, UpdateView

from audit.services import log_event

from .forms import PurchaseOrderForm, PurchaseOrderLineFormSet, ReceiveLineForm
from .models import POStatus, PurchaseOrder, PurchaseOrderLine
from .services import receive_lines


class POListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = PurchaseOrder
    template_name = 'procurement/po_list.html'
    context_object_name = 'purchase_orders'
    paginate_by = 30
    permission_required = 'procurement.view_purchaseorder'

    def get_queryset(self):
        qs = PurchaseOrder.objects.select_related('supplier', 'created_by')
        status = self.request.GET.get('status', '')
        if status in POStatus.values:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = POStatus.choices
        ctx['current_status'] = self.request.GET.get('status', '')
        return ctx


class PODetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = PurchaseOrder
    template_name = 'procurement/po_detail.html'
    context_object_name = 'po'
    permission_required = 'procurement.view_purchaseorder'

    def get_queryset(self):
        return PurchaseOrder.objects.select_related('supplier', 'created_by').prefetch_related(
            'lines__product',
        )


class POCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'procurement.add_purchaseorder'
    template_name = 'procurement/po_form.html'

    def _render(self, request, form, formset):
        from django.shortcuts import render
        return render(request, self.template_name, {'form': form, 'formset': formset, 'is_create': True})

    def get(self, request):
        return self._render(request, PurchaseOrderForm(), PurchaseOrderLineFormSet())

    def post(self, request):
        form = PurchaseOrderForm(request.POST)
        formset = PurchaseOrderLineFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            po = form.save(commit=False)
            po.created_by = request.user
            po.save()
            formset.instance = po
            formset.save()
            log_event(
                action='purchase_order.created',
                entity_type='PurchaseOrder',
                entity_id=po.pk,
                request=request,
                metadata={'ref': po.ref, 'supplier': str(po.supplier) if po.supplier else None},
            )
            messages.success(request, f'Purchase order {po.ref} created.')
            return redirect(po.get_absolute_url())
        return self._render(request, form, formset)


class POUpdateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'procurement.change_purchaseorder'
    template_name = 'procurement/po_form.html'

    def _get_po(self, pk):
        return get_object_or_404(PurchaseOrder, pk=pk)

    def _render(self, request, po, form, formset):
        from django.shortcuts import render
        return render(request, self.template_name, {'form': form, 'formset': formset, 'po': po, 'is_create': False})

    def get(self, request, pk):
        po = self._get_po(pk)
        if not po.is_editable:
            messages.warning(request, 'This purchase order can no longer be edited.')
            return redirect(po.get_absolute_url())
        return self._render(request, po, PurchaseOrderForm(instance=po), PurchaseOrderLineFormSet(instance=po))

    def post(self, request, pk):
        po = self._get_po(pk)
        if not po.is_editable:
            messages.warning(request, 'This purchase order can no longer be edited.')
            return redirect(po.get_absolute_url())
        form = PurchaseOrderForm(request.POST, instance=po)
        formset = PurchaseOrderLineFormSet(request.POST, instance=po)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            log_event(
                action='purchase_order.updated',
                entity_type='PurchaseOrder',
                entity_id=po.pk,
                request=request,
                metadata={'ref': po.ref},
            )
            messages.success(request, f'{po.ref} saved.')
            return redirect(po.get_absolute_url())
        return self._render(request, po, form, formset)


class POCancelView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Cancel a purchase order (only allowed when DRAFT or SENT)."""

    permission_required = 'procurement.change_purchaseorder'

    def post(self, request, pk):
        po = get_object_or_404(PurchaseOrder, pk=pk)
        if po.status not in (POStatus.DRAFT, POStatus.SENT):
            messages.error(request, f'Cannot cancel a PO with status "{po.get_status_display()}".')
            return redirect(po.get_absolute_url())
        po.status = POStatus.CANCELLED
        po.save(update_fields=['status'])
        log_event(
            action='purchase_order.cancelled',
            entity_type='PurchaseOrder',
            entity_id=po.pk,
            request=request,
            metadata={'ref': po.ref},
        )
        messages.success(request, f'Purchase order {po.ref} cancelled.')
        return redirect(po.get_absolute_url())


class POPrintView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = PurchaseOrder
    template_name = 'procurement/po_print.html'
    context_object_name = 'po'
    permission_required = 'procurement.view_purchaseorder'

    def get_queryset(self):
        return PurchaseOrder.objects.select_related('supplier', 'created_by').prefetch_related('lines__product')


class POReceiveView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Show outstanding lines and let staff enter received quantities + destination locations."""

    permission_required = 'procurement.change_purchaseorder'
    template_name = 'procurement/po_receive.html'

    def _get_po(self, pk):
        return get_object_or_404(PurchaseOrder, pk=pk)

    def _build_forms(self, lines, data=None):
        return [
            (line, ReceiveLineForm(data, prefix=str(line.pk), initial={'qty_to_receive': line.qty_outstanding}))
            for line in lines
        ]

    def get(self, request, pk):
        from django.shortcuts import render
        po = self._get_po(pk)
        if not po.can_receive:
            messages.warning(request, 'This purchase order cannot receive stock in its current status.')
            return redirect(po.get_absolute_url())
        outstanding = [ln for ln in po.lines.select_related('product') if ln.qty_outstanding > 0]
        line_forms = self._build_forms(outstanding)
        return render(request, self.template_name, {'po': po, 'line_forms': line_forms})

    def post(self, request, pk):
        from django.shortcuts import render
        po = self._get_po(pk)
        if not po.can_receive:
            messages.warning(request, 'This purchase order cannot receive stock in its current status.')
            return redirect(po.get_absolute_url())

        outstanding = [ln for ln in po.lines.select_related('product') if ln.qty_outstanding > 0]
        line_forms = self._build_forms(outstanding, data=request.POST)

        if all(f.is_valid() for _, f in line_forms):
            receipts = []
            for line, form in line_forms:
                qty = form.cleaned_data.get('qty_to_receive') or Decimal('0')
                location = form.cleaned_data.get('location')
                if qty > 0 and location:
                    receipts.append({'po_line': line, 'qty': qty, 'location': location})

            if receipts:
                receive_lines(po, receipts, request.user)
                log_event(
                    action='purchase_order.received',
                    entity_type='PurchaseOrder',
                    entity_id=po.pk,
                    request=request,
                    metadata={'ref': po.ref, 'lines_received': len(receipts)},
                )
                messages.success(request, f'Stock received against {po.ref}.')
            else:
                messages.info(request, 'No quantities entered.')
            return redirect(po.get_absolute_url())

        return render(request, self.template_name, {'po': po, 'line_forms': line_forms})
