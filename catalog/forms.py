from __future__ import annotations

from typing import Any, Iterator

from django import forms

from core.models import CURRENCY_CHOICES

from .models import Product, ProductImage, ProductOption
from .permissions import get_product_page_permissions


def _input_classes() -> str:
    return (
        'mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 '
        'shadow-sm focus:border-nova-500 focus:outline-none focus:ring-1 focus:ring-nova-500'
    )


def _checkbox_classes() -> str:
    return 'h-4 w-4 rounded border-slate-300 text-nova-600 focus:ring-nova-500'


# Order for the edit UI (sections). Omitted fields are skipped automatically.
_PRODUCT_FIELD_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        'General',
        (
            'name',
            'short_description',
            'long_description',
            'brand',
            'category',
            'status',
        ),
    ),
    (
        'Identification',
        ('sku', 'ean_gtin', 'mpn', 'upc_isbn'),
    ),
    (
        'Physical',
        (
            'length',
            'width',
            'height',
            'dimension_unit',
            'weight_net',
            'weight_gross',
            'weight_unit',
            'color',
            'material',
            'size_or_volume',
        ),
    ),
    (
        'Financial',
        (
            'purchase_price',
            'list_price',
            'msrp',
            'currency',
            'tax_rate',
            'discount_group',
        ),
    ),
    (
        'Logistics & stock',
        (
            'unit_of_measure',
            'minimum_order_quantity',
            'lead_time_days',
            'lead_time_text',
            'warehouse_location',
            'inventory_tracked',
        ),
    ),
    (
        'Asset & service',
        (
            'serial_number_required',
            'warranty_months',
            'maintenance_interval',
            'depreciation_months',
            'asset_type',
        ),
    ),
)


class ProductForm(forms.ModelForm):
    """Catalog product edit form; fields are trimmed per-user for future RBAC."""

    class Meta:
        model = Product
        exclude = ('id',)
        widgets = {
            'short_description': forms.Textarea(attrs={'rows': 2, 'class': _input_classes()}),
            'long_description': forms.Textarea(attrs={'rows': 6, 'class': _input_classes()}),
            'currency': forms.Select(
                choices=CURRENCY_CHOICES,
                attrs={'class': _input_classes()},
            ),
        }

    def __init__(self, *args: Any, user: Any | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.user = user
        css = _input_classes()
        for name, field in self.fields.items():
            if isinstance(
                field.widget,
                (forms.CheckboxInput, forms.ClearableFileInput),
            ):
                if isinstance(field.widget, forms.CheckboxInput):
                    field.widget.attrs['class'] = _checkbox_classes()
                continue
            if name not in self.Meta.widgets:
                field.widget.attrs.setdefault('class', css)

        if user is not None:
            perms = get_product_page_permissions(user, self.instance if self.instance.pk else None)
            if not perms['can_view_purchase_price']:
                self.fields.pop('purchase_price', None)
            if not perms['can_edit_financial']:
                for fname in (
                    'list_price',
                    'msrp',
                    'currency',
                    'tax_rate',
                    'discount_group',
                ):
                    self.fields.pop(fname, None)

    def iter_sections(self) -> Iterator[tuple[str, list[forms.BoundField]]]:
        for title, names in _PRODUCT_FIELD_SECTIONS:
            bound = [self[name] for name in names if name in self.fields]
            if bound:
                yield title, bound


class ProductImageUploadForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ('image', 'alt_text', 'is_primary', 'sort_order')

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields['image'].widget.attrs.setdefault(
            'class',
            'mt-1 block w-full text-sm text-slate-700 file:mr-4 file:rounded-lg file:border-0 '
            'file:bg-slate-700 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white '
            'hover:file:bg-slate-800',
        )
        self.fields['alt_text'].widget.attrs.setdefault('class', _input_classes())
        self.fields['is_primary'].widget.attrs.setdefault('class', _checkbox_classes())
        self.fields['sort_order'].widget.attrs.setdefault('class', _input_classes())


class ProductOptionForm(forms.ModelForm):
    """Add or edit a single option on a product."""

    class Meta:
        model = ProductOption
        fields = ('name', 'sku', 'price_delta', 'linked_product', 'is_required', 'is_default', 'sort_order')

    def __init__(self, *args: Any, parent_product: Product | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        css = _input_classes()
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault('class', _checkbox_classes())
            else:
                field.widget.attrs.setdefault('class', css)
        # Exclude the parent product itself from the linked_product dropdown
        if parent_product is not None:
            self.fields['linked_product'].queryset = (
                Product.objects.filter(is_archived=False)
                .exclude(pk=parent_product.pk)
                .order_by('name')
            )
        self.fields['linked_product'].required = False
        self.fields['linked_product'].help_text = (
            'Leave empty for a non-standalone option (e.g. cutter, network card). '
            'Set this to link an existing product that can also be sold on its own.'
        )
        self.fields['name'].help_text = 'Required when no linked product is set. When a linked product is set, leave blank to use the product\'s name or fill in to override it.'
        self.fields['sku'].help_text = 'Required when no linked product is set.'
        self.fields['price_delta'].help_text = 'Extra price added to the parent when selected. Ignored when a linked product is set (that product\'s list price is used).'
