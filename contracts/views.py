from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView
from django.utils import timezone

from .forms import (
    ContractForm,
    ContractTemplateForm,
    ServiceRateForm,
    TemplateVariableFormSet,
    VariableValueFormSet,
)
from .models import (
    Contract,
    ContractTemplate,
    ContractTemplateVariable,
    ContractVariableType,
    ContractVariableValue,
    ServiceRate,
)
from .services import (
    build_variable_context,
    create_variable_value_stubs,
    refresh_computed_result,
    validate_formula,
)


# ──────────────────────────────────────────────────────────────────────────────
# Service Rates
# ──────────────────────────────────────────────────────────────────────────────

class ServiceRateListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'contracts.view_servicerate'
    model               = ServiceRate
    template_name       = 'contracts/service_rate_list.html'
    context_object_name = 'rates'

    def get_queryset(self):
        return ServiceRate.objects.all()


class ServiceRateCreateView(LoginRequiredMixin, CreateView):
    model         = ServiceRate
    form_class    = ServiceRateForm
    template_name = 'contracts/service_rate_form.html'
    success_url   = reverse_lazy('contracts:rate_list')


class ServiceRateUpdateView(LoginRequiredMixin, UpdateView):
    model         = ServiceRate
    form_class    = ServiceRateForm
    template_name = 'contracts/service_rate_form.html'
    success_url   = reverse_lazy('contracts:rate_list')


# ──────────────────────────────────────────────────────────────────────────────
# Contract Templates
# ──────────────────────────────────────────────────────────────────────────────

class _TemplateMixin:
    """Shared create/update logic for ContractTemplate with inline variable formset."""

    def _get_variable_formset(self, **kwargs):
        if self.request.POST:
            return TemplateVariableFormSet(self.request.POST, instance=self.object, **kwargs)
        return TemplateVariableFormSet(instance=self.object, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if 'variable_formset' not in ctx:
            ctx['variable_formset'] = self._get_variable_formset()
        return ctx

    def post(self, request, *args, **kwargs):
        # For UpdateView self.object is already set; for CreateView we need to set it.
        if not hasattr(self, 'object') or self.object is None:
            self.object = None
        form = self.get_form()
        formset = self._get_variable_formset()
        if form.is_valid() and formset.is_valid():
            return self._save_all(form, formset)
        return self.render_to_response(
            self.get_context_data(form=form, variable_formset=formset)
        )

    def _save_all(self, form, formset):
        self.object = form.save()
        formset.instance = self.object
        formset.save()
        # Validate formula against saved variables
        var_names = list(self.object.variables.values_list('name', flat=True))
        error = validate_formula(self.object.formula, var_names)
        if error:
            form.add_error('formula', f'Formula references: {error}')
            return self.render_to_response(
                self.get_context_data(form=form, variable_formset=formset)
            )
        return HttpResponseRedirect(self.object.get_absolute_url())


class ContractTemplateListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'contracts.view_contracttemplate'
    model               = ContractTemplate
    template_name       = 'contracts/template_list.html'
    context_object_name = 'templates'


class ContractTemplateDetailView(LoginRequiredMixin, DetailView):
    model               = ContractTemplate
    template_name       = 'contracts/template_detail.html'
    context_object_name = 'tmpl'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['variables'] = self.object.variables.select_related('service_rate').order_by('sort_order', 'name')
        ctx['contracts'] = self.object.contracts.select_related('organization').order_by('-created_at')[:10]
        return ctx


class ContractTemplateCreateView(_TemplateMixin, LoginRequiredMixin, CreateView):
    model         = ContractTemplate
    form_class    = ContractTemplateForm
    template_name = 'contracts/template_form.html'

    def get(self, request, *args, **kwargs):
        self.object = None
        return super().get(request, *args, **kwargs)


class ContractTemplateUpdateView(_TemplateMixin, LoginRequiredMixin, UpdateView):
    model         = ContractTemplate
    form_class    = ContractTemplateForm
    template_name = 'contracts/template_form.html'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().post(request, *args, **kwargs)


# ──────────────────────────────────────────────────────────────────────────────
# Contracts
# ──────────────────────────────────────────────────────────────────────────────

class ContractListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'contracts.view_contract'
    model               = Contract
    template_name       = 'contracts/contract_list.html'
    context_object_name = 'contracts'
    paginate_by         = 25

    def get_queryset(self):
        qs = Contract.objects.select_related('organization', 'template')
        status = self.request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(reference__icontains=q) | qs.filter(organization__name__icontains=q)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from .models import ContractStatus
        ctx['status_choices'] = ContractStatus.choices
        ctx['current_status'] = self.request.GET.get('status', '')
        ctx['q'] = self.request.GET.get('q', '')
        return ctx


class ContractDetailView(LoginRequiredMixin, DetailView):
    model               = Contract
    template_name       = 'contracts/contract_detail.html'
    context_object_name = 'contract'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        contract = self.object
        variables, missing = build_variable_context(contract)

        # Build variable rows for display
        rows = []
        BUILTIN_LABELS = {
            'duration_years':       ('Duration (years)',        ''),
            'duration_months':      ('Duration (months)',       ''),
            'quote_total':          ('Quote total',             contract.quote.reference if contract.quote_id else ''),
            'order_total':          ('Order total',             contract.sales_order.reference if contract.sales_order_id else ''),
            'asset_purchase_price': ('Asset purchase price',    ''),
        }

        for var in contract.template.variables.select_related('service_rate').order_by('sort_order', 'name'):
            value = variables.get(var.name)
            rows.append({
                'name':  var.name,
                'label': var.label,
                'type':  var.get_variable_type_display(),
                'unit':  var.unit,
                'value': value,
                'missing': var.name in missing,
                'source': (
                    var.service_rate.name if var.variable_type == ContractVariableType.SERVICE_RATE and var.service_rate
                    else f'= {var.constant_value}' if var.variable_type == ContractVariableType.CONSTANT
                    else 'user input'
                ),
            })

        ctx['variable_rows'] = rows
        ctx['missing'] = missing

        # Use cached result or compute on-the-fly for display
        if contract.computed_result is not None:
            ctx['computed_result'] = contract.computed_result
            ctx['compute_error'] = None
        else:
            from .services import compute_contract
            result, error = compute_contract(contract)
            ctx['computed_result'] = result
            ctx['compute_error'] = error

        # VAT breakdown on computed result
        self._add_vat_context(ctx, contract)
        return ctx

    @staticmethod
    def _add_vat_context(ctx, contract):
        from decimal import Decimal
        result = ctx.get('computed_result')
        if result is not None and contract.tax_rate_id:
            rate = contract.tax_rate.rate
            vat_amount = (result * rate / 100).quantize(Decimal('0.01'))
            ctx['contract_vat_rate'] = rate
            ctx['contract_vat_amount'] = vat_amount
            ctx['contract_grand_total'] = result + vat_amount
        else:
            ctx['contract_vat_rate'] = None
            ctx['contract_vat_amount'] = None
            ctx['contract_grand_total'] = result


class ContractCreateView(LoginRequiredMixin, CreateView):
    model         = Contract
    form_class    = ContractForm
    template_name = 'contracts/contract_form.html'

    def get(self, request, *args, **kwargs):
        self.object = None
        return super().get(request, *args, **kwargs)

    def form_valid(self, form):
        from django.utils import timezone
        from core.models import next_reference
        contract = form.save(commit=False)
        contract.reference = next_reference('SVC', timezone.now().year)
        contract.save()
        create_variable_value_stubs(contract)
        refresh_computed_result(contract)
        return HttpResponseRedirect(contract.get_absolute_url())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['is_create'] = True
        return ctx


class ContractPrintView(LoginRequiredMixin, DetailView):
    model = Contract
    template_name = 'contracts/contract_print.html'
    context_object_name = 'contract'

    def get_queryset(self):
        return Contract.objects.select_related(
            'organization', 'template', 'quote', 'sales_order', 'asset',
        ).prefetch_related('template__variables', 'variable_values__variable')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        contract = self.object
        variables, missing = build_variable_context(contract)
        rows = []
        for var in contract.template.variables.select_related('service_rate').order_by('sort_order', 'name'):
            value = variables.get(var.name)
            rows.append({
                'label': var.label,
                'unit': var.unit,
                'value': value,
            })
        ctx['variable_rows'] = rows
        if contract.computed_result is not None:
            ctx['computed_result'] = contract.computed_result
        else:
            from .services import compute_contract
            result, _error = compute_contract(contract)
            ctx['computed_result'] = result
        ContractDetailView._add_vat_context(ctx, contract)
        return ctx


class ContractUpdateView(LoginRequiredMixin, UpdateView):
    model         = Contract
    form_class    = ContractForm
    template_name = 'contracts/contract_form.html'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().get(request, *args, **kwargs)

    def _get_value_qs(self):
        return (
            ContractVariableValue.objects
            .filter(contract=self.object)
            .select_related('variable')
            .order_by('variable__sort_order', 'variable__name')
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if 'value_formset' not in ctx:
            ctx['value_formset'] = VariableValueFormSet(
                instance=self.object,
                queryset=self._get_value_qs(),
            )
        ctx['is_create'] = False
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form    = self.get_form()
        formset = VariableValueFormSet(
            request.POST,
            instance=self.object,
            queryset=self._get_value_qs(),
        )
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            refresh_computed_result(self.object)
            return HttpResponseRedirect(self.object.get_absolute_url())
        return self.render_to_response(
            self.get_context_data(form=form, value_formset=formset)
        )
