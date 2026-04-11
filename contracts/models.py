from __future__ import annotations

import ast
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import UUIDPrimaryKeyModel, next_reference

MONEY = dict(max_digits=12, decimal_places=2)

# ──────────────────────────────────────────────────────────────────────────────
# Service Rates
# ──────────────────────────────────────────────────────────────────────────────

class ServiceRate(UUIDPrimaryKeyModel):
    """Managed lookup for hourly/service rates used in contract formula variables."""

    name = models.CharField(max_length=200)
    code = models.SlugField(
        max_length=50,
        unique=True,
        help_text='Short identifier (e.g. mechanic, engineer). Used as the variable name in formulas.',
    )
    description = models.TextField(blank=True)
    rate_per_hour = models.DecimalField(**MONEY)
    currency = models.CharField(max_length=3, default='EUR')
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = 'service rate'
        verbose_name_plural = 'service rates'
        ordering = ['name']

    def __str__(self) -> str:
        return f'{self.name} ({self.currency} {self.rate_per_hour}/h)'

    def get_absolute_url(self) -> str:
        from django.urls import reverse
        return reverse('contracts:rate_update', kwargs={'pk': self.pk})


# ──────────────────────────────────────────────────────────────────────────────
# Contract Templates
# ──────────────────────────────────────────────────────────────────────────────

class ContractVariableType(models.TextChoices):
    USER_INPUT   = 'user_input',   'User input'
    SERVICE_RATE = 'service_rate', 'Service rate'
    CONSTANT     = 'constant',     'Constant'


class ContractTemplate(UUIDPrimaryKeyModel):
    """
    Reusable blueprint for contract cost formulas.
    Defines a formula string and the named variables it references.
    """

    name         = models.CharField(max_length=200)
    description  = models.TextField(blank=True)
    formula      = models.TextField(
        help_text=(
            'Python-style arithmetic expression. Allowed operators: + − * / ( ). '
            'Use variable names defined below plus built-ins: '
            'duration_years, duration_months, quote_total, order_total, asset_purchase_price.'
        )
    )
    result_label = models.CharField(
        max_length=100,
        default='Annual cost',
        help_text='Label shown next to the computed result (e.g. "Annual cost" or "Total contract value").',
    )
    is_active = models.BooleanField(default=True, db_index=True)
    notes     = models.TextField(blank=True)

    class Meta:
        verbose_name        = 'contract template'
        verbose_name_plural = 'contract templates'
        ordering            = ['name']

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        from django.urls import reverse
        return reverse('contracts:template_detail', kwargs={'pk': self.pk})

    def clean(self) -> None:
        super().clean()
        if self.formula:
            try:
                ast.parse(self.formula.strip(), mode='eval')
            except SyntaxError as exc:
                raise ValidationError({'formula': f'Invalid formula syntax: {exc}'})


class ContractTemplateVariable(UUIDPrimaryKeyModel):
    """A named variable referenced inside a ContractTemplate formula."""

    template      = models.ForeignKey(ContractTemplate, on_delete=models.CASCADE, related_name='variables')
    name          = models.CharField(
        max_length=80,
        help_text='Python identifier used in the formula (e.g. mechanic_hours, setup_fee).',
    )
    label         = models.CharField(max_length=200, help_text='Human-readable label shown in the UI.')
    variable_type = models.CharField(max_length=20, choices=ContractVariableType)
    service_rate  = models.ForeignKey(
        ServiceRate,
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='template_variables',
        help_text='Required when type is "Service rate".',
    )
    constant_value = models.DecimalField(
        max_digits=18, decimal_places=6,
        null=True, blank=True,
        help_text='Fixed value. Required when type is "Constant".',
    )
    default_value = models.DecimalField(
        max_digits=18, decimal_places=6,
        null=True, blank=True,
        help_text='Default value pre-filled for user input fields.',
    )
    unit       = models.CharField(max_length=50, blank=True, help_text='Display unit (e.g. hours, %, EUR).')
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name        = 'template variable'
        verbose_name_plural = 'template variables'
        ordering            = ['sort_order', 'name']
        unique_together     = ('template', 'name')

    def __str__(self) -> str:
        return f'{self.template.name} / {self.name}'

    def clean(self) -> None:
        super().clean()
        if self.name and not self.name.isidentifier():
            raise ValidationError(
                {'name': 'Name must be a valid identifier (letters, digits, underscores; no spaces).'}
            )
        RESERVED = {'duration_years', 'duration_months', 'quote_total', 'order_total', 'asset_purchase_price'}
        if self.name in RESERVED:
            raise ValidationError(
                {'name': f'"{self.name}" is a built-in variable and cannot be redefined here.'}
            )
        if self.variable_type == ContractVariableType.SERVICE_RATE and not self.service_rate_id:
            raise ValidationError({'service_rate': 'Select a service rate for this variable type.'})
        if self.variable_type == ContractVariableType.CONSTANT and self.constant_value is None:
            raise ValidationError({'constant_value': 'Enter a constant value for this variable type.'})

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def resolved_value(self) -> Decimal | None:
        """Return the value for constant/service_rate types, None for user_input."""
        if self.variable_type == ContractVariableType.SERVICE_RATE and self.service_rate:
            return Decimal(str(self.service_rate.rate_per_hour))
        if self.variable_type == ContractVariableType.CONSTANT and self.constant_value is not None:
            return Decimal(str(self.constant_value))
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Contracts
# ──────────────────────────────────────────────────────────────────────────────

class ContractStatus(models.TextChoices):
    DRAFT      = 'draft',      'Draft'
    ACTIVE     = 'active',     'Active'
    EXPIRED    = 'expired',    'Expired'
    TERMINATED = 'terminated', 'Terminated'


class Contract(UUIDPrimaryKeyModel):
    """
    A customer contract instance computed from a ContractTemplate formula.
    """

    reference    = models.CharField(max_length=32, unique=True, db_index=True)
    template     = models.ForeignKey(ContractTemplate, on_delete=models.PROTECT, related_name='contracts')
    organization = models.ForeignKey(
        'relations.Organization',
        on_delete=models.PROTECT,
        related_name='contracts',
        verbose_name='customer organization',
    )
    status     = models.CharField(
        max_length=20, choices=ContractStatus, default=ContractStatus.DRAFT, db_index=True
    )
    start_date = models.DateField(null=True, blank=True)
    end_date   = models.DateField(null=True, blank=True)
    quote = models.ForeignKey(
        'sales.Quote',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='contracts',
        verbose_name='linked quote',
    )
    sales_order = models.ForeignKey(
        'sales.SalesOrder',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='contracts',
        verbose_name='linked sales order',
    )
    asset = models.ForeignKey(
        'assets.Asset',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='contracts',
        verbose_name='linked asset',
    )
    tax_rate = models.ForeignKey(
        'catalog.TaxRate',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='contracts',
        verbose_name='VAT rate',
        help_text='VAT rate applied to the computed contract value.',
    )
    notes = models.TextField(blank=True)

    # Cached computation
    computed_result = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    computed_at     = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'contract'
        verbose_name_plural = 'contracts'
        ordering            = ['-created_at']

    def __str__(self) -> str:
        return f'{self.reference} - {self.organization}'

    def get_absolute_url(self) -> str:
        from django.urls import reverse
        return reverse('contracts:contract_detail', kwargs={'pk': self.pk})

    def clean(self) -> None:
        super().clean()
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValidationError({'end_date': 'End date must be after the start date.'})

    @property
    def duration_years(self) -> Decimal | None:
        if self.start_date and self.end_date:
            return Decimal(str(round((self.end_date - self.start_date).days / 365.25, 6)))
        return None

    @property
    def duration_months(self) -> Decimal | None:
        if self.start_date and self.end_date:
            return Decimal(str(round((self.end_date - self.start_date).days / 30.4375, 6)))
        return None


class ContractVariableValue(UUIDPrimaryKeyModel):
    """Stores the user-supplied value for a user_input template variable on a specific contract."""

    contract  = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='variable_values')
    variable  = models.ForeignKey(
        ContractTemplateVariable,
        on_delete=models.CASCADE,
        related_name='contract_values',
    )
    value = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('0'))

    class Meta:
        verbose_name        = 'variable value'
        verbose_name_plural = 'variable values'
        unique_together     = ('contract', 'variable')
        ordering            = ['variable__sort_order', 'variable__name']

    def __str__(self) -> str:
        return f'{self.contract.reference} / {self.variable.name} = {self.value}'
