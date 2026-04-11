from __future__ import annotations

from django import forms
from django.forms import inlineformset_factory

from inventory.models import StockLocation
from .models import PurchaseOrder, PurchaseOrderLine


def _css() -> str:
    return (
        'mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 '
        'shadow-sm focus:border-nova-500 focus:outline-none focus:ring-1 focus:ring-nova-500'
    )


class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ['supplier', 'status', 'expected_delivery_date', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
            'expected_delivery_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        css = _css()
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', css)


class PurchaseOrderLineForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrderLine
        fields = ['product', 'description', 'qty_ordered', 'unit_cost']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        css = _css()
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', css)
        self.fields['description'].required = False
        self.fields['unit_cost'].required = False


PurchaseOrderLineFormSet = inlineformset_factory(
    PurchaseOrder,
    PurchaseOrderLine,
    form=PurchaseOrderLineForm,
    extra=3,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


class ReceiveLineForm(forms.Form):
    """One row in the receive screen: qty to receive + destination location."""

    qty_to_receive = forms.DecimalField(
        max_digits=12, decimal_places=3,
        min_value=0,
        required=False,
    )
    location = forms.ModelChoiceField(
        queryset=StockLocation.objects.filter(is_active=True).select_related('warehouse'),
        required=False,
        empty_label='- select location -',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        css = _css()
        self.fields['qty_to_receive'].widget.attrs.update({'class': css, 'step': '0.001'})
        self.fields['location'].widget.attrs.update({'class': css})

    def clean(self):
        cleaned = super().clean()
        qty = cleaned.get('qty_to_receive') or 0
        location = cleaned.get('location')
        if qty > 0 and not location:
            self.add_error('location', 'Select a destination location.')
        return cleaned
