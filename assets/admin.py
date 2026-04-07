from django.contrib import admin

from .models import (
    Asset,
    AssetComponent,
    AssetEvent,
    AssetOrganizationTransfer,
    AssetRecallLink,
    AssetReplacementRecommendation,
    MaintenancePlan,
    MaintenancePlanLine,
    RecallCampaign,
)


class AssetComponentInline(admin.TabularInline):
    model = AssetComponent
    extra = 0
    raw_id_fields = ('order_line', 'product_option')
    fields = ('name', 'sku', 'price', 'installed_at', 'product_option', 'notes')


class AssetOrganizationTransferInline(admin.TabularInline):
    model = AssetOrganizationTransfer
    extra = 0
    readonly_fields = (
        'from_organization',
        'to_organization',
        'transferred_by',
        'transferred_at',
        'note',
    )
    can_delete = False

    def has_add_permission(self, request, obj=None) -> bool:
        return False


class AssetEventInline(admin.TabularInline):
    model = AssetEvent
    extra = 0
    readonly_fields = ('created_at',)
    raw_id_fields = ('related_product', 'recall_campaign', 'created_by')


class AssetRecallLinkInline(admin.TabularInline):
    model = AssetRecallLink
    extra = 0
    raw_id_fields = ('asset',)


class ReplacementRecommendationInline(admin.TabularInline):
    model = AssetReplacementRecommendation
    extra = 0
    raw_id_fields = ('suggested_product', 'created_by')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = (
        'display_name',
        'organization',
        'product',
        'serial_number',
        'status',
        'expected_end_of_life_date',
        'is_archived',
        'created_at',
    )
    list_filter = ('status', 'is_archived')
    search_fields = ('name', 'serial_number', 'asset_tag', 'notes', 'location_note')
    raw_id_fields = ('organization', 'person', 'product', 'order_line', 'parent_asset', 'created_by')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [
        AssetComponentInline,
        AssetOrganizationTransferInline,
        AssetEventInline,
        AssetRecallLinkInline,
        ReplacementRecommendationInline,
    ]

    @admin.display(description='Name')
    def display_name(self, obj: Asset) -> str:
        return obj.display_name()


class AssetRecallLinkCampaignInline(admin.TabularInline):
    model = AssetRecallLink
    extra = 0
    raw_id_fields = ('asset',)


@admin.register(RecallCampaign)
class RecallCampaignAdmin(admin.ModelAdmin):
    list_display = ('reference', 'title', 'product', 'is_active', 'announced_date', 'is_archived')
    list_filter = ('is_active', 'is_archived')
    search_fields = ('reference', 'title', 'description')
    raw_id_fields = ('product', 'created_by')
    inlines = [AssetRecallLinkCampaignInline]


@admin.register(AssetEvent)
class AssetEventAdmin(admin.ModelAdmin):
    list_display = ('title', 'asset', 'event_type', 'occurred_on', 'created_by')
    list_filter = ('event_type',)
    search_fields = ('title', 'description', 'reference_external')
    raw_id_fields = ('asset', 'related_product', 'recall_campaign', 'created_by')


@admin.register(AssetRecallLink)
class AssetRecallLinkAdmin(admin.ModelAdmin):
    list_display = ('recall_campaign', 'asset', 'status', 'completed_on')
    list_filter = ('status',)
    raw_id_fields = ('recall_campaign', 'asset')


class MaintenancePlanLineInline(admin.TabularInline):
    model = MaintenancePlanLine
    extra = 0
    raw_id_fields = ('related_asset', 'recommended_product')


@admin.register(MaintenancePlan)
class MaintenancePlanAdmin(admin.ModelAdmin):
    list_display = ('reference', 'name', 'organization', 'status', 'valid_from', 'valid_until')
    list_filter = ('status', 'is_archived')
    search_fields = ('reference', 'name', 'notes')
    raw_id_fields = ('organization', 'created_by')
    inlines = [MaintenancePlanLineInline]


@admin.register(MaintenancePlanLine)
class MaintenancePlanLineAdmin(admin.ModelAdmin):
    list_display = ('plan', 'plan_year', 'title', 'is_promoted', 'line_status')
    list_filter = ('plan_year', 'is_promoted', 'line_status')
    search_fields = ('title', 'description')
    raw_id_fields = ('plan', 'related_asset', 'recommended_product')


@admin.register(AssetReplacementRecommendation)
class AssetReplacementRecommendationAdmin(admin.ModelAdmin):
    list_display = ('asset', 'suggested_product', 'priority', 'status', 'created_at')
    list_filter = ('priority', 'status', 'is_archived')
    raw_id_fields = ('asset', 'suggested_product', 'created_by')
