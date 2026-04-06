from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.shortcuts import redirect
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import AssignmentFormSet, PricingRuleForm
from .models import PricingRule
from .services import preview_products_for_rule


class PricingRuleListView(LoginRequiredMixin, ListView):
    model               = PricingRule
    context_object_name = 'rules'
    template_name       = 'pricing/rule_list.html'

    def get_queryset(self):
        return PricingRule.objects.prefetch_related('assignments').order_by('name')


class PricingRuleDetailView(LoginRequiredMixin, DetailView):
    model               = PricingRule
    context_object_name = 'rule'
    template_name       = 'pricing/rule_detail.html'

    def get_queryset(self):
        return PricingRule.objects.prefetch_related(
            'assignments__product',
            'assignments__category',
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['preview'] = preview_products_for_rule(self.object)
        return ctx


class _RuleFormMixin:
    """Shared form_valid / form_invalid logic for create and update."""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx['assignment_formset'] = AssignmentFormSet(
                self.request.POST,
                instance=getattr(self, 'object', None),
            )
        else:
            ctx['assignment_formset'] = AssignmentFormSet(
                instance=getattr(self, 'object', None),
            )
        return ctx

    def form_valid(self, form):
        ctx = self.get_context_data()
        formset = ctx['assignment_formset']
        if not formset.is_valid():
            return self.render_to_response(
                self.get_context_data(form=form)
            )
        self.object = form.save()
        formset.instance = self.object
        formset.save()
        verb = 'created' if isinstance(self, PricingRuleCreateView) else 'updated'
        messages.success(self.request, f'Pricing rule "{self.object.name}" {verb}.')
        return redirect(self.object.get_absolute_url())

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


class PricingRuleCreateView(_RuleFormMixin, LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model               = PricingRule
    form_class          = PricingRuleForm
    template_name       = 'pricing/rule_form.html'
    permission_required = 'pricing.add_pricingrule'


class PricingRuleUpdateView(_RuleFormMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model               = PricingRule
    form_class          = PricingRuleForm
    template_name       = 'pricing/rule_form.html'
    permission_required = 'pricing.change_pricingrule'
