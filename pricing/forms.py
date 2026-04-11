from __future__ import annotations

from django import forms
from django.forms import inlineformset_factory

from .models import PricingRule, PricingRuleAssignment, RoundingMethod


def _input_cls() -> str:
    return (
        'mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 '
        'shadow-sm focus:border-nova-500 focus:outline-none focus:ring-1 focus:ring-nova-500'
    )


def _checkbox_cls() -> str:
    return 'h-4 w-4 rounded border-slate-300 text-nova-600 focus:ring-nova-500'


class PricingRuleForm(forms.ModelForm):
    class Meta:
        model  = PricingRule
        fields = [
            'name', 'description', 'method', 'value',
            'rounding', 'rounding_increment', 'is_active', 'notes',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'notes':       forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cls = _input_cls()
        chk = _checkbox_cls()
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault('class', chk)
            else:
                field.widget.attrs.setdefault('class', cls)
        self.fields['rounding_increment'].required = False

    def clean(self):
        cleaned = super().clean()
        rounding  = cleaned.get('rounding')
        increment = cleaned.get('rounding_increment')
        if rounding == RoundingMethod.CUSTOM and not increment:
            self.add_error(
                'rounding_increment',
                'A positive increment is required for custom rounding.',
            )
        return cleaned


class PricingRuleAssignmentForm(forms.ModelForm):
    class Meta:
        model  = PricingRuleAssignment
        fields = ['product', 'category', 'include_subcategories', 'priority']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cls = _input_cls()
        chk = _checkbox_cls()
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault('class', chk)
            else:
                field.widget.attrs.setdefault('class', cls)
        self.fields['product'].required  = False
        self.fields['category'].required = False
        self.fields['product'].empty_label  = '- select product -'
        self.fields['category'].empty_label = '- select category -'


AssignmentFormSet = inlineformset_factory(
    PricingRule,
    PricingRuleAssignment,
    form=PricingRuleAssignmentForm,
    extra=1,
    can_delete=True,
    max_num=50,
)
