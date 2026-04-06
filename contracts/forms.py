from __future__ import annotations

from django import forms
from django.forms import inlineformset_factory

from .models import (
    Contract,
    ContractTemplate,
    ContractTemplateVariable,
    ContractVariableType,
    ContractVariableValue,
    ServiceRate,
)

# Shared widget classes
_INPUT   = 'mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-nova-500 focus:outline-none focus:ring-1 focus:ring-nova-500'
_SELECT  = 'mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-nova-500 focus:outline-none focus:ring-1 focus:ring-nova-500 bg-white'
_AREA    = 'mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-nova-500 focus:outline-none focus:ring-1 focus:ring-nova-500 resize-y'
_CHECK   = 'h-4 w-4 rounded border-slate-300 text-nova-600 focus:ring-nova-500'
_SLUG    = _INPUT + ' font-mono'


# ──────────────────────────────────────────────────────────────────────────────
# Service Rate
# ──────────────────────────────────────────────────────────────────────────────

class ServiceRateForm(forms.ModelForm):
    class Meta:
        model  = ServiceRate
        fields = ['name', 'code', 'description', 'rate_per_hour', 'currency', 'is_active']
        widgets = {
            'name':         forms.TextInput(attrs={'class': _INPUT}),
            'code':         forms.TextInput(attrs={'class': _SLUG}),
            'description':  forms.Textarea(attrs={'class': _AREA, 'rows': 3}),
            'rate_per_hour': forms.NumberInput(attrs={'class': _INPUT, 'step': '0.01', 'min': '0'}),
            'currency':     forms.TextInput(attrs={'class': _INPUT, 'maxlength': '3'}),
            'is_active':    forms.CheckboxInput(attrs={'class': _CHECK}),
        }


# ──────────────────────────────────────────────────────────────────────────────
# Contract Template
# ──────────────────────────────────────────────────────────────────────────────

class ContractTemplateForm(forms.ModelForm):
    class Meta:
        model  = ContractTemplate
        fields = ['name', 'description', 'formula', 'result_label', 'is_active', 'notes']
        widgets = {
            'name':         forms.TextInput(attrs={'class': _INPUT}),
            'description':  forms.Textarea(attrs={'class': _AREA, 'rows': 2}),
            'formula':      forms.Textarea(attrs={'class': _AREA + ' font-mono', 'rows': 4}),
            'result_label': forms.TextInput(attrs={'class': _INPUT}),
            'is_active':    forms.CheckboxInput(attrs={'class': _CHECK}),
            'notes':        forms.Textarea(attrs={'class': _AREA, 'rows': 3}),
        }

    def clean(self):
        cleaned = super().clean()
        formula = cleaned.get('formula', '')
        # Validate formula against known variable names
        if formula and self.instance.pk:
            var_names = list(
                self.instance.variables.values_list('name', flat=True)
            )
            from .services import validate_formula
            error = validate_formula(formula, var_names)
            if error:
                self.add_error('formula', error)
        return cleaned


class ContractTemplateVariableForm(forms.ModelForm):
    class Meta:
        model  = ContractTemplateVariable
        fields = [
            'name', 'label', 'variable_type', 'service_rate',
            'constant_value', 'default_value', 'unit', 'sort_order',
        ]
        widgets = {
            'name':           forms.TextInput(attrs={'class': _SLUG}),
            'label':          forms.TextInput(attrs={'class': _INPUT}),
            'variable_type':  forms.Select(attrs={'class': _SELECT + ' var-type-select'}),
            'service_rate':   forms.Select(attrs={'class': _SELECT + ' service-rate-field'}),
            'constant_value': forms.NumberInput(attrs={'class': _INPUT + ' constant-value-field', 'step': 'any'}),
            'default_value':  forms.NumberInput(attrs={'class': _INPUT, 'step': 'any'}),
            'unit':           forms.TextInput(attrs={'class': _INPUT}),
            'sort_order':     forms.NumberInput(attrs={'class': _INPUT, 'min': '0'}),
        }


TemplateVariableFormSet = inlineformset_factory(
    ContractTemplate,
    ContractTemplateVariable,
    form=ContractTemplateVariableForm,
    extra=1,
    can_delete=True,
)


# ──────────────────────────────────────────────────────────────────────────────
# Contract
# ──────────────────────────────────────────────────────────────────────────────

class ContractForm(forms.ModelForm):
    class Meta:
        model  = Contract
        fields = [
            'template', 'organization', 'status',
            'start_date', 'end_date',
            'quote', 'sales_order', 'asset',
            'notes',
        ]
        widgets = {
            'template':     forms.Select(attrs={'class': _SELECT}),
            'organization': forms.Select(attrs={'class': _SELECT}),
            'status':       forms.Select(attrs={'class': _SELECT}),
            'start_date':   forms.DateInput(attrs={'class': _INPUT, 'type': 'date'}),
            'end_date':     forms.DateInput(attrs={'class': _INPUT, 'type': 'date'}),
            'quote':        forms.Select(attrs={'class': _SELECT}),
            'sales_order':  forms.Select(attrs={'class': _SELECT}),
            'asset':        forms.Select(attrs={'class': _SELECT}),
            'notes':        forms.Textarea(attrs={'class': _AREA, 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Limit to active templates only
        self.fields['template'].queryset = ContractTemplate.objects.filter(is_active=True)
        self.fields['template'].empty_label = '— select template —'
        self.fields['organization'].empty_label = '— select organisation —'
        self.fields['quote'].empty_label = '— none —'
        self.fields['sales_order'].empty_label = '— none —'
        self.fields['asset'].empty_label = '— none —'


class ContractVariableValueForm(forms.ModelForm):
    class Meta:
        model   = ContractVariableValue
        fields  = ['value']
        widgets = {
            'value': forms.NumberInput(attrs={'class': _INPUT, 'step': 'any'}),
        }


VariableValueFormSet = inlineformset_factory(
    Contract,
    ContractVariableValue,
    form=ContractVariableValueForm,
    extra=0,
    can_delete=False,
)
