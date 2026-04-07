from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from catalog.models import Product
from core.models import UUIDPrimaryKeyModel

MONEY = dict(max_digits=12, decimal_places=2)


class AssetStatus(models.TextChoices):
    PENDING_INSTALL = 'pending_install', 'Pending installation'
    IN_SERVICE = 'in_service', 'In service'
    UNDER_REPAIR = 'under_repair', 'Under repair'
    WARRANTY = 'warranty', 'In warranty'
    END_OF_LIFE_NEAR = 'eol_near', 'End of life — plan replacement'
    RETIRED = 'retired', 'Retired'
    DISPOSED = 'disposed', 'Disposed'


class Asset(UUIDPrimaryKeyModel):
    """
    Customer-site equipment: purchase history, lifespan, and service anchor for recalls and maintenance plans.
    """

    organization = models.ForeignKey(
        'relations.Organization',
        on_delete=models.PROTECT,
        related_name='customer_assets',
        verbose_name='customer organization',
    )
    person = models.ForeignKey(
        'relations.Person',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='assets_owned',
        verbose_name='contact / owner',
        help_text='Optional person at the organization.',
    )
    product = models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='customer_assets',
        verbose_name='product',
    )
    parent_asset = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='sub_assets',
        verbose_name='parent asset',
        help_text='Set when this asset was installed as an option/add-on of another asset.',
    )
    order_line = models.ForeignKey(
        'sales.OrderLine',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='assets',
        verbose_name='order line',
        help_text='Optional link to the sales order line that sourced this unit.',
    )
    name = models.CharField(
        max_length=255,
        blank=True,
        help_text='Optional display name; UI falls back to product name.',
    )
    serial_number = models.CharField(max_length=120, blank=True, db_index=True)
    asset_tag = models.CharField(
        max_length=80,
        blank=True,
        db_index=True,
        verbose_name='internal asset tag',
    )
    purchase_date = models.DateField(null=True, blank=True)
    installation_date = models.DateField(null=True, blank=True)
    warranty_end_date = models.DateField(null=True, blank=True)
    expected_end_of_life_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='expected end of life',
        help_text='Planned replacement horizon for multi-year maintenance planning and sales advice.',
    )
    status = models.CharField(
        max_length=24,
        choices=AssetStatus,
        default=AssetStatus.IN_SERVICE,
        db_index=True,
    )
    location_note = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='location',
        help_text='Site, room, rack, etc.',
    )
    notes = models.TextField(blank=True)

    is_archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='assets_created',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'asset'
        verbose_name_plural = 'assets'
        indexes = [
            models.Index(fields=['organization', 'is_archived']),
        ]

    def __str__(self) -> str:
        label = self.display_name()
        return f'{label} @ {self.organization.name}'

    def display_name(self) -> str:
        if self.name.strip():
            return self.name.strip()
        if self.product_id:
            return self.product.name
        return 'Asset'

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse('assets:asset_detail', kwargs={'pk': self.pk})

    def clean(self) -> None:
        super().clean()
        if self.organization_id and not self.organization.is_customer_or_prospect_relation():
            raise ValidationError(
                {
                    'organization': 'Assets may only be registered for organizations tagged as Customer or Prospect.',
                },
            )


class AssetComponent(UUIDPrimaryKeyModel):
    """
    A non-standalone option physically installed as part of an asset
    (e.g. a printer cutter, network interface card).

    For standalone product-as-option add-ons (e.g. a customer display sold alongside a POS),
    a separate Asset record with parent_asset set is used instead.
    """

    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name='components',
        verbose_name='asset',
    )
    name = models.CharField(max_length=200, verbose_name='component name')
    sku = models.CharField(max_length=100, blank=True, verbose_name='SKU')
    price = models.DecimalField(**MONEY, null=True, blank=True, verbose_name='price at installation')
    installed_at = models.DateField(
        null=True, blank=True, default=timezone.localdate, verbose_name='installed on',
    )
    order_line = models.ForeignKey(
        'sales.OrderLine',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='asset_components',
        verbose_name='order line',
    )
    product_option = models.ForeignKey(
        'catalog.ProductOption',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='asset_components',
        verbose_name='product option',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['asset', 'installed_at', 'name']
        verbose_name = 'asset component'
        verbose_name_plural = 'asset components'

    def __str__(self) -> str:
        return f'{self.name} on {self.asset}'


class AssetOrganizationTransfer(UUIDPrimaryKeyModel):
    """Append-only record when an asset is assigned to a different customer organization."""

    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name='organization_transfers',
    )
    from_organization = models.ForeignKey(
        'relations.Organization',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='asset_transfers_from',
        verbose_name='from organization',
        help_text='Previous custodian; empty for initial registration.',
    )
    to_organization = models.ForeignKey(
        'relations.Organization',
        on_delete=models.PROTECT,
        related_name='asset_transfers_to',
        verbose_name='to organization',
    )
    transferred_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='asset_organization_transfers_recorded',
    )
    transferred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-transferred_at']
        verbose_name = 'asset organization transfer'
        verbose_name_plural = 'asset organization transfers'

    def __str__(self) -> str:
        return f'{self.asset_id}: {self.from_organization_id} → {self.to_organization_id}'


class AssetEventType(models.TextChoices):
    INSTALLATION = 'installation', 'Installation'
    REPAIR = 'repair', 'Repair'
    INSPECTION = 'inspection', 'Inspection'
    RECALL_SERVICE = 'recall_service', 'Recall / safety service'
    CALIBRATION = 'calibration', 'Calibration'
    WARRANTY_CLAIM = 'warranty_claim', 'Warranty claim'
    RECOMMENDATION = 'recommendation', 'Advisory / upsell note'
    NOTE = 'note', 'General note'
    OTHER = 'other', 'Other'


class AssetEvent(UUIDPrimaryKeyModel):
    """Timeline entry: repairs, inspections, recalls, recommendations."""

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=32, choices=AssetEventType, db_index=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    occurred_on = models.DateField(default=timezone.localdate, db_index=True)
    vendor_name = models.CharField(max_length=200, blank=True, verbose_name='vendor / technician')
    reference_external = models.CharField(
        max_length=120,
        blank=True,
        verbose_name='external reference',
        help_text='RMA, work order, or ticket ID.',
    )
    cost_amount = models.DecimalField(**MONEY, null=True, blank=True)
    cost_currency = models.CharField(max_length=3, blank=True, default='EUR')
    related_product = models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='asset_events',
        verbose_name='related product',
        help_text='Spare part or replacement SKU, if applicable.',
    )
    recall_campaign = models.ForeignKey(
        'RecallCampaign',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='asset_events',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='asset_events_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-occurred_on', '-created_at']
        verbose_name = 'asset event'
        verbose_name_plural = 'asset events'

    def __str__(self) -> str:
        return f'{self.get_event_type_display()}: {self.title}'


class RecallCampaign(UUIDPrimaryKeyModel):
    """Manufacturer or regulatory recall affecting one or more installed assets."""

    reference = models.CharField(max_length=32, unique=True, db_index=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    remedy_description = models.TextField(
        blank=True,
        verbose_name='remedy / action required',
    )
    product = models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='recall_campaigns',
        help_text='Optional filter: typical product family affected.',
    )
    announced_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    is_archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='recall_campaigns_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-announced_date', '-created_at']
        verbose_name = 'recall campaign'
        verbose_name_plural = 'recall campaigns'

    def __str__(self) -> str:
        return f'{self.reference} — {self.title}'

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse('assets:recall_detail', kwargs={'pk': self.pk})


class AssetRecallStatus(models.TextChoices):
    PENDING = 'pending', 'Pending assessment'
    ACTION_REQUIRED = 'action_required', 'Action required'
    IN_PROGRESS = 'in_progress', 'Remedy in progress'
    COMPLETED = 'completed', 'Completed'
    NOT_AFFECTED = 'not_affected', 'Not affected'
    EXEMPT = 'exempt', 'Exempt / waived'


class AssetRecallLink(UUIDPrimaryKeyModel):
    """Links a specific installed asset to a recall campaign."""

    recall_campaign = models.ForeignKey(
        RecallCampaign,
        on_delete=models.CASCADE,
        related_name='asset_links',
    )
    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name='recall_links',
    )
    status = models.CharField(
        max_length=24,
        choices=AssetRecallStatus,
        default=AssetRecallStatus.PENDING,
        db_index=True,
    )
    completed_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['recall_campaign', 'asset']
        verbose_name = 'asset recall link'
        verbose_name_plural = 'asset recall links'
        constraints = [
            models.UniqueConstraint(
                fields=['recall_campaign', 'asset'],
                name='assets_assetrecalllink_unique_campaign_asset',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.recall_campaign.reference} ↔ {self.asset}'


class MaintenancePlanStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    ACTIVE = 'active', 'Active'
    ARCHIVED = 'archived', 'Archived'


class MaintenancePlan(UUIDPrimaryKeyModel):
    """
    Multi-year maintenance plan (MJOP): maintenance and replacement outlook for a customer over multiple years.
    """

    reference = models.CharField(max_length=32, unique=True, db_index=True)
    organization = models.ForeignKey(
        'relations.Organization',
        on_delete=models.PROTECT,
        related_name='maintenance_plans',
        verbose_name='customer organization',
    )
    name = models.CharField(max_length=255)
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=MaintenancePlanStatus,
        default=MaintenancePlanStatus.DRAFT,
        db_index=True,
    )
    notes = models.TextField(blank=True)

    is_archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='maintenance_plans_created',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-valid_from', '-created_at']
        verbose_name = 'multi-year maintenance plan (MJOP)'
        verbose_name_plural = 'multi-year maintenance plans (MJOP)'

    def __str__(self) -> str:
        return f'{self.reference} — {self.name}'

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse('assets:mjop_detail', kwargs={'pk': self.pk})

    def clean(self) -> None:
        super().clean()
        if self.organization_id and not self.organization.is_customer_or_prospect_relation():
            raise ValidationError(
                {
                    'organization': 'A maintenance plan may only be linked to organizations tagged as Customer or Prospect.',
                },
            )


class MaintenancePlanLineStatus(models.TextChoices):
    PLANNED = 'planned', 'Planned'
    SCHEDULED = 'scheduled', 'Scheduled'
    IN_PROGRESS = 'in_progress', 'In progress'
    COMPLETED = 'completed', 'Completed'
    DEFERRED = 'deferred', 'Deferred'
    CANCELLED = 'cancelled', 'Cancelled'


class MaintenancePlanLine(UUIDPrimaryKeyModel):
    """One row in a multi-year maintenance plan: year bucket, optional asset, promoted replacement advice."""

    plan = models.ForeignKey(
        MaintenancePlan,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    plan_year = models.PositiveIntegerField(
        db_index=True,
        help_text='Calendar year this line applies to (e.g. 2027).',
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    related_asset = models.ForeignKey(
        Asset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='mjop_lines',
        verbose_name='related asset',
    )
    recommended_product = models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='mjop_line_recommendations',
        verbose_name='recommended product',
        help_text='SKU or bundle to propose (replacement, upgrade, service kit).',
    )
    is_promoted = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name='promote to customer',
        help_text='Highlight in customer-facing maintenance plan summaries and sales follow-up.',
    )
    estimated_cost_note = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='estimated cost (note)',
        help_text='Indicative budget text; not a quote.',
    )
    line_status = models.CharField(
        max_length=20,
        choices=MaintenancePlanLineStatus,
        default=MaintenancePlanLineStatus.PLANNED,
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['plan', 'plan_year', 'sort_order', 'id']
        verbose_name = 'maintenance plan line'
        verbose_name_plural = 'maintenance plan lines'

    def __str__(self) -> str:
        return f'{self.plan_year}: {self.title}'


class ReplacementPriority(models.TextChoices):
    LOW = 'low', 'Low'
    MEDIUM = 'medium', 'Medium'
    HIGH = 'high', 'High'


class ReplacementRecommendationStatus(models.TextChoices):
    OPEN = 'open', 'Open'
    ACCEPTED = 'accepted', 'Accepted'
    DISMISSED = 'dismissed', 'Dismissed'
    SUPERSEDED = 'superseded', 'Superseded'


class AssetReplacementRecommendation(UUIDPrimaryKeyModel):
    """Sales-facing queue: propose a catalog item to replace or upgrade an installed asset."""

    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name='replacement_recommendations',
    )
    suggested_product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='replacement_recommendations_from',
    )
    rationale = models.TextField(blank=True)
    priority = models.CharField(
        max_length=16,
        choices=ReplacementPriority,
        default=ReplacementPriority.MEDIUM,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=ReplacementRecommendationStatus,
        default=ReplacementRecommendationStatus.OPEN,
        db_index=True,
    )

    is_archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='replacement_recommendations_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'replacement recommendation'
        verbose_name_plural = 'replacement recommendations'

    def __str__(self) -> str:
        return f'{self.suggested_product.sku} for {self.asset.display_name()}'


def next_recall_reference() -> str:
    from core.models import next_reference
    return next_reference('REC', timezone.now().year, pad=4)


def next_mjop_reference() -> str:
    from core.models import next_reference
    return next_reference('MJOP', timezone.now().year, pad=4)
