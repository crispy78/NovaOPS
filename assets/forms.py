from __future__ import annotations

from decimal import Decimal

from django import forms
from django.db.models import Q

from catalog.models import Product
from relations.models import Organization, Person

from .models import (
    Asset,
    AssetEvent,
    AssetRecallLink,
    AssetReplacementRecommendation,
    MaintenancePlan,
    MaintenancePlanLine,
    RecallCampaign,
)


def _input_class() -> str:
    return (
        'mt-1 w-full max-w-xl rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 '
        'shadow-sm focus:border-nova-500 focus:outline-none focus:ring-1 focus:ring-nova-500'
    )


def customer_prospect_organizations():
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


class AssetForm(forms.ModelForm):
    class Meta:
        model = Asset
        fields = (
            'organization',
            'person',
            'product',
            'name',
            'serial_number',
            'asset_tag',
            'purchase_date',
            'installation_date',
            'warranty_end_date',
            'expected_end_of_life_date',
            'status',
            'location_note',
            'notes',
        )
        widgets = {
            'organization': forms.Select(attrs={'class': _input_class()}),
            'person': forms.Select(attrs={'class': _input_class()}),
            'product': forms.Select(attrs={'class': _input_class()}),
            'name': forms.TextInput(attrs={'class': _input_class()}),
            'serial_number': forms.TextInput(attrs={'class': _input_class()}),
            'asset_tag': forms.TextInput(attrs={'class': _input_class()}),
            'purchase_date': forms.DateInput(attrs={'class': _input_class(), 'type': 'date'}),
            'installation_date': forms.DateInput(attrs={'class': _input_class(), 'type': 'date'}),
            'warranty_end_date': forms.DateInput(attrs={'class': _input_class(), 'type': 'date'}),
            'expected_end_of_life_date': forms.DateInput(attrs={'class': _input_class(), 'type': 'date'}),
            'status': forms.Select(attrs={'class': _input_class()}),
            'location_note': forms.TextInput(attrs={'class': _input_class()}),
            'notes': forms.Textarea(attrs={'class': _input_class(), 'rows': 4}),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields['organization'].queryset = customer_prospect_organizations()
        self.fields['person'].queryset = Person.objects.filter(is_archived=False).order_by(
            'last_name', 'first_name',
        )
        self.fields['product'].queryset = Product.objects.filter(is_archived=False).order_by('name')
        self.fields['person'].required = False
        self.fields['product'].required = False


class AssetEventForm(forms.ModelForm):
    class Meta:
        model = AssetEvent
        fields = (
            'event_type',
            'title',
            'description',
            'occurred_on',
            'vendor_name',
            'reference_external',
            'cost_amount',
            'cost_currency',
            'related_product',
            'recall_campaign',
        )
        widgets = {
            'event_type': forms.Select(attrs={'class': _input_class()}),
            'title': forms.TextInput(attrs={'class': _input_class()}),
            'description': forms.Textarea(attrs={'class': _input_class(), 'rows': 3}),
            'occurred_on': forms.DateInput(attrs={'class': _input_class(), 'type': 'date'}),
            'vendor_name': forms.TextInput(attrs={'class': _input_class()}),
            'reference_external': forms.TextInput(attrs={'class': _input_class()}),
            'cost_amount': forms.NumberInput(attrs={'class': _input_class(), 'step': '0.01'}),
            'cost_currency': forms.TextInput(attrs={'class': _input_class(), 'maxlength': 3}),
            'related_product': forms.Select(attrs={'class': _input_class()}),
            'recall_campaign': forms.Select(attrs={'class': _input_class()}),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields['related_product'].queryset = Product.objects.filter(is_archived=False).order_by('name')
        self.fields['related_product'].required = False
        self.fields['recall_campaign'].queryset = RecallCampaign.objects.filter(
            is_archived=False,
        ).order_by('-announced_date', 'reference')
        self.fields['recall_campaign'].required = False
        self.fields['cost_amount'].required = False
        self.fields['cost_currency'].initial = 'EUR'

    def clean_cost_amount(self):
        val = self.cleaned_data.get('cost_amount')
        if val is not None and val < Decimal('0'):
            raise forms.ValidationError('Cost cannot be negative.')
        return val


class RecallCampaignForm(forms.ModelForm):
    class Meta:
        model = RecallCampaign
        fields = (
            'title',
            'description',
            'remedy_description',
            'product',
            'announced_date',
            'is_active',
        )
        widgets = {
            'title': forms.TextInput(attrs={'class': _input_class()}),
            'description': forms.Textarea(attrs={'class': _input_class(), 'rows': 4}),
            'remedy_description': forms.Textarea(attrs={'class': _input_class(), 'rows': 3}),
            'product': forms.Select(attrs={'class': _input_class()}),
            'announced_date': forms.DateInput(attrs={'class': _input_class(), 'type': 'date'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-slate-300 text-nova-600'}),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.filter(is_archived=False).order_by('name')
        self.fields['product'].required = False


class AssetRecallLinkForm(forms.ModelForm):
    class Meta:
        model = AssetRecallLink
        fields = ('asset', 'status', 'completed_on', 'notes')
        widgets = {
            'asset': forms.Select(attrs={'class': _input_class()}),
            'status': forms.Select(attrs={'class': _input_class()}),
            'completed_on': forms.DateInput(attrs={'class': _input_class(), 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': _input_class(), 'rows': 2}),
        }

    def __init__(self, *args, campaign: RecallCampaign | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields['asset'].queryset = (
            Asset.objects.filter(is_archived=False)
            .select_related('organization', 'product')
            .order_by('organization__name', 'serial_number', 'name')
        )
        self.fields['completed_on'].required = False
        self._campaign = campaign

    def clean(self):
        data = super().clean()
        asset = data.get('asset')
        if self._campaign and asset:
            if AssetRecallLink.objects.filter(recall_campaign=self._campaign, asset=asset).exists():
                raise forms.ValidationError('This asset is already linked to this recall.')
        return data


class RecallLinkStatusForm(forms.ModelForm):
    """Lightweight form for updating the status of an existing asset recall link."""

    class Meta:
        model = AssetRecallLink
        fields = ('status', 'completed_on', 'notes')
        widgets = {
            'status': forms.Select(attrs={'class': _input_class()}),
            'completed_on': forms.DateInput(attrs={'class': _input_class(), 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': _input_class(), 'rows': 2}),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields['completed_on'].required = False
        self.fields['notes'].required = False


class MaintenancePlanForm(forms.ModelForm):
    class Meta:
        model = MaintenancePlan
        fields = ('organization', 'name', 'valid_from', 'valid_until', 'status', 'notes')
        widgets = {
            'organization': forms.Select(attrs={'class': _input_class()}),
            'name': forms.TextInput(attrs={'class': _input_class()}),
            'valid_from': forms.DateInput(attrs={'class': _input_class(), 'type': 'date'}),
            'valid_until': forms.DateInput(attrs={'class': _input_class(), 'type': 'date'}),
            'status': forms.Select(attrs={'class': _input_class()}),
            'notes': forms.Textarea(attrs={'class': _input_class(), 'rows': 3}),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields['organization'].queryset = customer_prospect_organizations()
        self.fields['valid_until'].required = False


class MaintenancePlanLineForm(forms.ModelForm):
    class Meta:
        model = MaintenancePlanLine
        fields = (
            'plan_year',
            'sort_order',
            'title',
            'description',
            'related_asset',
            'recommended_product',
            'is_promoted',
            'estimated_cost_note',
            'line_status',
        )
        widgets = {
            'plan_year': forms.NumberInput(attrs={'class': _input_class(), 'min': 2000, 'max': 2100}),
            'sort_order': forms.NumberInput(attrs={'class': _input_class(), 'min': 0}),
            'title': forms.TextInput(attrs={'class': _input_class()}),
            'description': forms.Textarea(attrs={'class': _input_class(), 'rows': 3}),
            'related_asset': forms.Select(attrs={'class': _input_class()}),
            'recommended_product': forms.Select(attrs={'class': _input_class()}),
            'is_promoted': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-slate-300 text-nova-600'}),
            'estimated_cost_note': forms.TextInput(attrs={'class': _input_class()}),
            'line_status': forms.Select(attrs={'class': _input_class()}),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields['related_asset'].queryset = Asset.objects.filter(is_archived=False).order_by(
            '-created_at',
        )
        self.fields['related_asset'].required = False
        self.fields['recommended_product'].queryset = Product.objects.filter(is_archived=False).order_by(
            'name',
        )
        self.fields['recommended_product'].required = False


class ReplacementRecommendationForm(forms.ModelForm):
    class Meta:
        model = AssetReplacementRecommendation
        fields = ('suggested_product', 'rationale', 'priority', 'status')
        widgets = {
            'suggested_product': forms.Select(attrs={'class': _input_class()}),
            'rationale': forms.Textarea(attrs={'class': _input_class(), 'rows': 3}),
            'priority': forms.Select(attrs={'class': _input_class()}),
            'status': forms.Select(attrs={'class': _input_class()}),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields['suggested_product'].queryset = Product.objects.filter(is_archived=False).order_by('name')
