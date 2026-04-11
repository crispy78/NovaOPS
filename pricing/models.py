from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from core.models import UUIDPrimaryKeyModel


class PricingMethod(models.TextChoices):
    COST_MARKUP      = 'cost_markup',      'Cost + markup %'
    GROSS_MARGIN     = 'gross_margin',     'Gross margin %'
    MSRP_DISCOUNT    = 'msrp_discount',    'MSRP − discount %'
    LIST_DISCOUNT    = 'list_discount',    'List price − discount %'
    FIXED_MULTIPLIER = 'fixed_multiplier', 'Fixed multiplier (cost × factor)'


class RoundingMethod(models.TextChoices):
    NONE         = 'none',         'None (exact)'
    NEAREST_CENT = 'nearest_cent', 'Nearest cent (0.01)'
    NEAREST_10C  = 'nearest_10c',  'Nearest 10 cents (0.10)'
    NEAREST_50C  = 'nearest_50c',  'Nearest 50 cents (0.50)'
    NEAREST_EURO = 'nearest_euro', 'Nearest whole unit (1.00)'
    NEAREST_5    = 'nearest_5',    'Nearest 5'
    NEAREST_10   = 'nearest_10',   'Nearest 10'
    CUSTOM       = 'custom',       'Custom increment'


class PricingRule(UUIDPrimaryKeyModel):
    """
    A named strategy for computing a selling price from a source price field.
    Assigned to products or categories via PricingRuleAssignment.
    """
    name        = models.CharField(max_length=200, verbose_name='name')
    description = models.TextField(blank=True, verbose_name='description')
    method      = models.CharField(
        max_length=30,
        choices=PricingMethod,
        verbose_name='pricing method',
    )
    value = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        verbose_name='method value',
        help_text=(
            'Markup %, gross margin %, or discount % (0–100). '
            'For "Fixed multiplier" enter the factor directly (e.g. 1.35 for 35% above cost).'
        ),
    )
    rounding = models.CharField(
        max_length=20,
        choices=RoundingMethod,
        default=RoundingMethod.NEAREST_CENT,
        verbose_name='rounding',
    )
    rounding_increment = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name='custom rounding increment',
        help_text='Required when rounding is "Custom increment" (e.g. 0.05 or 2.50).',
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name='active')
    notes     = models.TextField(blank=True, verbose_name='internal notes')

    class Meta:
        verbose_name        = 'pricing rule'
        verbose_name_plural = 'pricing rules'
        ordering            = ['name']

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        from django.urls import reverse
        return reverse('pricing:rule_detail', kwargs={'pk': self.pk})

    def clean(self) -> None:
        super().clean()
        if self.rounding == RoundingMethod.CUSTOM:
            if not self.rounding_increment or self.rounding_increment <= 0:
                raise ValidationError(
                    {'rounding_increment': 'A positive increment is required for custom rounding.'}
                )
        if self.value is not None:
            if self.method == PricingMethod.GROSS_MARGIN and self.value >= 100:
                raise ValidationError({'value': 'Gross margin % must be less than 100.'})
            if self.method in (PricingMethod.MSRP_DISCOUNT, PricingMethod.LIST_DISCOUNT):
                if self.value < 0 or self.value > 100:
                    raise ValidationError({'value': 'Discount % must be between 0 and 100.'})
            if self.method == PricingMethod.FIXED_MULTIPLIER and self.value <= 0:
                raise ValidationError({'value': 'Multiplier must be greater than 0.'})

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def method_value_display(self) -> str:
        """Human-readable summary, e.g. 'Cost + 35.00%' or 'MSRP − 10.00%'."""
        v = self.value
        match self.method:
            case PricingMethod.COST_MARKUP:
                return f'Cost + {v:.2f}%'
            case PricingMethod.GROSS_MARGIN:
                return f'{v:.2f}% gross margin'
            case PricingMethod.MSRP_DISCOUNT:
                return f'MSRP − {v:.2f}%'
            case PricingMethod.LIST_DISCOUNT:
                return f'List price − {v:.2f}%'
            case PricingMethod.FIXED_MULTIPLIER:
                return f'Cost × {v:.4f}'
            case _:
                return str(v)


class PricingRuleAssignment(UUIDPrimaryKeyModel):
    """
    Links a PricingRule to either a specific Product or a ProductCategory.
    Exactly one of product / category must be set.
    """
    rule = models.ForeignKey(
        PricingRule,
        on_delete=models.CASCADE,
        related_name='assignments',
        verbose_name='pricing rule',
    )
    product = models.ForeignKey(
        'catalog.Product',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='pricing_assignments',
        verbose_name='product',
    )
    category = models.ForeignKey(
        'catalog.ProductCategory',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='pricing_assignments',
        verbose_name='category',
    )
    include_subcategories = models.BooleanField(
        default=True,
        verbose_name='include subcategories',
        help_text='Also apply this rule to all descendant categories.',
    )
    priority = models.PositiveSmallIntegerField(
        default=10,
        verbose_name='priority',
        help_text='Lower number = higher priority when multiple rules could apply.',
    )

    class Meta:
        verbose_name        = 'pricing rule assignment'
        verbose_name_plural = 'pricing rule assignments'
        ordering            = ['priority', 'rule__name']

    def __str__(self) -> str:
        target = self.product or self.category or '-'
        return f'{self.rule.name} → {target}'

    def clean(self) -> None:
        super().clean()
        has_product  = bool(self.product_id)
        has_category = bool(self.category_id)
        if has_product and has_category:
            raise ValidationError('Set either a product or a category - not both.')
        if not has_product and not has_category:
            raise ValidationError('Set either a product or a category.')
        if has_product:
            self.include_subcategories = False

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)
