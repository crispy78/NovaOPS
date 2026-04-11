from decimal import Decimal

from django import forms
from django.db.models import Q
from django.forms import inlineformset_factory

from catalog.models import Product
from relations.models import Organization

from .models import FulfillmentOrder, Quote, QuoteLine, ShippingOrder

from .services import fulfillment_line_unallocated_quantity, shipping_order_line_unshipped_quantity


def _sales_input_class() -> str:
    return (
        'mt-1 w-full max-w-xl rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 '
        'shadow-sm focus:border-nova-500 focus:outline-none focus:ring-1 focus:ring-nova-500'
    )


def quote_relation_organizations():
    """Organizations usable as quote counterparty: Customer or Prospect (primary or tag)."""
    return (
        Organization.objects.filter(is_archived=False)
        .filter(
            Q(primary_category__code__in=('customer', 'prospect'))
            | Q(categories__code__in=('customer', 'prospect'))
        )
        .distinct()
        .select_related('primary_category')
        .order_by('name')
    )


class CreateQuoteFromCartForm(forms.Form):
    relation_organization = forms.ModelChoiceField(
        queryset=Organization.objects.none(),
        label='Customer / prospect',
        required=True,
        help_text='Only organizations tagged as Customer or Prospect are listed.',
    )
    internal_reference = forms.CharField(
        max_length=80,
        required=False,
        label='Internal reference ID',
        widget=forms.TextInput(attrs={'class': _sales_input_class(), 'placeholder': 'e.g. internal deal ID'}),
    )
    external_reference = forms.CharField(
        max_length=80,
        required=False,
        label='External reference ID',
        widget=forms.TextInput(attrs={'class': _sales_input_class(), 'placeholder': 'e.g. customer RFQ number'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['relation_organization'].queryset = quote_relation_organizations()
        self.fields['relation_organization'].widget.attrs.setdefault('class', _sales_input_class())

    def clean_relation_organization(self):
        org = self.cleaned_data['relation_organization']
        if org is not None and not org.is_customer_or_prospect_relation():
            raise forms.ValidationError('That organization is not tagged as Customer or Prospect.')
        return org


class CreateOrderFromCartForm(forms.Form):
    relation_organization = forms.ModelChoiceField(
        queryset=Organization.objects.none(),
        label='Customer / prospect',
        required=True,
        help_text='Only organizations tagged as Customer or Prospect are listed.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['relation_organization'].queryset = quote_relation_organizations()
        self.fields['relation_organization'].widget.attrs.setdefault('class', _sales_input_class())

    def clean_relation_organization(self):
        org = self.cleaned_data['relation_organization']
        if org is not None and not org.is_customer_or_prospect_relation():
            raise forms.ValidationError('That organization is not tagged as Customer or Prospect.')
        return org


class QuoteHeaderForm(forms.ModelForm):
    class Meta:
        model = Quote
        fields = (
            'relation_organization',
            'status',
            'valid_until',
            'internal_reference',
            'external_reference',
            'notes',
        )
        widgets = {
            'internal_reference': forms.TextInput(attrs={'class': _sales_input_class()}),
            'external_reference': forms.TextInput(attrs={'class': _sales_input_class()}),
            'valid_until': forms.DateInput(attrs={'type': 'date', 'class': _sales_input_class()}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': _sales_input_class()}),
            'status': forms.Select(attrs={'class': _sales_input_class()}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['relation_organization'].queryset = quote_relation_organizations()
        self.fields['relation_organization'].required = True
        self.fields['relation_organization'].widget.attrs.setdefault('class', _sales_input_class())
        self.fields['relation_organization'].help_text = (
            'Customer or prospect organization this quote is for.'
        )

    def clean_relation_organization(self):
        org = self.cleaned_data.get('relation_organization')
        if org is not None and not org.is_customer_or_prospect_relation():
            raise forms.ValidationError('That organization is not tagged as Customer or Prospect.')
        return org


class AddToCartForm(forms.Form):
    quantity = forms.IntegerField(
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={'class': 'qty-stepper-input', 'min': '1'}),
    )


class CartLineQuantityForm(forms.Form):
    quantity = forms.IntegerField(
        min_value=0,
        widget=forms.NumberInput(
            attrs={
                'class': 'w-24 rounded-lg border border-slate-300 px-2 py-1 text-sm',
            },
        ),
        help_text='Set to 0 to remove.',
    )


class ReplacementPickForm(forms.Form):
    """Pick a catalog product as the formal replacement for EOL / discontinued items."""

    replacement_product = forms.ModelChoiceField(
        queryset=Product.objects.all(),
        label='Replacement product',
        widget=forms.Select(attrs={'class': 'mt-1 w-full max-w-md rounded-lg border border-slate-300 px-3 py-2 text-sm'}),
    )

    def __init__(self, *args, exclude_product_ids=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Product.objects.order_by('name')
        if exclude_product_ids:
            qs = qs.exclude(pk__in=exclude_product_ids)
        self.fields['replacement_product'].queryset = qs


class QuoteLineEditForm(forms.ModelForm):
    class Meta:
        model = QuoteLine
        fields = ('quantity', 'unit_price', 'currency')
        widgets = {
            'quantity': forms.NumberInput(attrs={'class': 'w-24 rounded border border-slate-300 px-2 py-1 text-sm'}),
            'unit_price': forms.NumberInput(attrs={'class': 'w-32 rounded border border-slate-300 px-2 py-1 text-sm', 'step': '0.01'}),
            'currency': forms.TextInput(attrs={'class': 'w-20 rounded border border-slate-300 px-2 py-1 text-sm', 'maxlength': 3}),
        }


QuoteLineFormSet = inlineformset_factory(
    Quote,
    QuoteLine,
    form=QuoteLineEditForm,
    extra=0,
    can_delete=False,
)


class InvoicePaymentForm(forms.Form):
    amount = forms.DecimalField(
        min_value=Decimal('0.01'),
        max_digits=14,
        decimal_places=2,
        label='Payment amount',
        widget=forms.NumberInput(attrs={'class': _sales_input_class(), 'step': '0.01'}),
    )
    reference_note = forms.CharField(
        max_length=120,
        required=False,
        label='Payment reference',
        widget=forms.TextInput(attrs={'class': _sales_input_class(), 'placeholder': 'Bank ref, check no., …'}),
    )

    def __init__(self, *args, max_amount=None, **kwargs):
        super().__init__(*args, **kwargs)
        if max_amount is not None:
            self.fields['amount'].max_value = max_amount
            self.fields['amount'].widget.attrs['max'] = str(max_amount)


def make_create_shipping_order_form(fulfillment: FulfillmentOrder) -> type[forms.Form]:
    """Dynamic form: one optional qty field per fulfillment line (max = unallocated)."""
    field_defs: dict = {}
    for fl in fulfillment.lines.order_by('sort_order', 'id'):
        rem = fulfillment_line_unallocated_quantity(fl)
        name = f'qty_{fl.pk}'
        field_defs[name] = forms.IntegerField(
            required=False,
            min_value=0,
            max_value=max(rem, 0),
            initial=rem if rem > 0 else 0,
            label=f'{fl.product_name} ({fl.sku})',
            help_text=f'Up to {rem} left to allocate on a shipping order.',
            widget=forms.NumberInput(
                attrs={'class': _sales_input_class(), 'min': 0, 'max': max(rem, 0), 'style': 'max-width:8rem'},
            ),
        )
    field_defs['notes'] = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': _sales_input_class(), 'rows': 2}),
        label='Notes',
    )
    return type('CreateShippingOrderForm', (forms.Form,), field_defs)


class ShipmentHeaderForm(forms.Form):
    carrier = forms.CharField(
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={'class': _sales_input_class(), 'placeholder': 'Carrier name'}),
    )
    tracking_number = forms.CharField(
        max_length=120,
        required=False,
        label='Tracking number',
        widget=forms.TextInput(attrs={'class': _sales_input_class()}),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': _sales_input_class(), 'rows': 2}),
    )


def make_shipment_lines_form(shipping_order: ShippingOrder) -> type[forms.Form]:
    """Dynamic form: qty per shipping order line (max = not yet on a shipment)."""
    field_defs: dict = {}
    for sol in shipping_order.lines.select_related('fulfillment_line').order_by('id'):
        unsh = shipping_order_line_unshipped_quantity(sol)
        fl = sol.fulfillment_line
        name = f'qty_{sol.pk}'
        field_defs[name] = forms.IntegerField(
            required=False,
            min_value=0,
            max_value=max(unsh, 0),
            initial=unsh if unsh > 0 else 0,
            label=f'{fl.product_name} ({fl.sku}) - line qty {sol.quantity}',
            help_text=f'Up to {unsh} not yet assigned to a parcel/shipment.',
            widget=forms.NumberInput(
                attrs={'class': _sales_input_class(), 'min': 0, 'max': max(unsh, 0), 'style': 'max-width:8rem'},
            ),
        )
    return type('ShipmentLinesForm', (forms.Form,), field_defs)
