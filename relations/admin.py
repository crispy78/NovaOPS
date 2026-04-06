from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline

from . import models


class AddressInline(GenericTabularInline):
    model = models.Address
    extra = 0


class OrganizationCommunicationInline(GenericTabularInline):
    model = models.Communication
    extra = 0
    fields = ('comm_type', 'label', 'value', 'is_primary')


class PersonCommunicationInline(GenericTabularInline):
    model = models.Communication
    extra = 0
    fields = ('comm_type', 'label', 'value', 'is_primary', 'employer_organization')
    autocomplete_fields = ('employer_organization',)


class SocialProfileInline(GenericTabularInline):
    model = models.SocialProfile
    extra = 0


class AffiliationInline(admin.TabularInline):
    model = models.Affiliation
    extra = 0
    autocomplete_fields = ('organization', 'person')


class SpecialEventInline(admin.TabularInline):
    model = models.SpecialEvent
    extra = 0


class OrganizationLinkFromInline(admin.TabularInline):
    model = models.OrganizationLink
    fk_name = 'from_organization'
    extra = 0
    autocomplete_fields = ('to_organization',)


@admin.register(models.Organization)
class OrganizationAdmin(admin.ModelAdmin):
    readonly_fields = ('id', 'created_at', 'updated_at')
    list_display = ('name', 'parent', 'unit_kind', 'is_archived')
    list_filter = ('is_archived', 'unit_kind')
    search_fields = ('name', 'legal_name')
    autocomplete_fields = ('parent',)
    filter_horizontal = ('categories',)
    inlines = (
        AddressInline,
        OrganizationCommunicationInline,
        SocialProfileInline,
        AffiliationInline,
        OrganizationLinkFromInline,
    )

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(models.Person)
class PersonAdmin(admin.ModelAdmin):
    readonly_fields = ('id', 'created_at', 'updated_at')
    list_display = ('last_name', 'first_name', 'date_of_birth', 'is_archived')
    list_filter = ('is_archived',)
    search_fields = ('first_name', 'last_name')
    inlines = (
        AddressInline,
        PersonCommunicationInline,
        SocialProfileInline,
        AffiliationInline,
        SpecialEventInline,
    )

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(models.OrganizationLinkType)
class OrganizationLinkTypeAdmin(admin.ModelAdmin):
    readonly_fields = ('id',)
    list_display = ('id', 'name')
    search_fields = ('name',)


@admin.register(models.OrganizationCategoryTag)
class OrganizationCategoryTagAdmin(admin.ModelAdmin):
    readonly_fields = ('id',)
    list_display = ('code', 'label')
    search_fields = ('code', 'label')


@admin.register(models.OrganizationLink)
class OrganizationLinkAdmin(admin.ModelAdmin):
    readonly_fields = ('id',)
    list_display = ('from_organization', 'link_type', 'to_organization', 'start_date', 'end_date')
    list_filter = ('link_type',)
    search_fields = ('from_organization__name', 'to_organization__name')
    autocomplete_fields = ('from_organization', 'to_organization', 'link_type')


@admin.register(models.Affiliation)
class AffiliationAdmin(admin.ModelAdmin):
    readonly_fields = ('id',)
    list_display = ('person', 'organization', 'job_title', 'is_primary', 'start_date', 'end_date')
    list_filter = ('end_date',)
    search_fields = ('person__first_name', 'person__last_name', 'organization__name', 'job_title')
    autocomplete_fields = ('person', 'organization')


@admin.register(models.SpecialEvent)
class SpecialEventAdmin(admin.ModelAdmin):
    readonly_fields = ('id',)
    list_display = ('person', 'name', 'event_date')
    list_filter = ('event_date',)
    search_fields = ('person__first_name', 'person__last_name', 'name', 'notes')
    autocomplete_fields = ('person',)


@admin.register(models.Address)
class AddressAdmin(admin.ModelAdmin):
    readonly_fields = ('id',)
    list_display = ('id', 'address_type', 'label', 'city', 'country')
    list_filter = ('address_type', 'country')
    search_fields = ('label', 'street', 'city', 'zipcode', 'country')


@admin.register(models.Communication)
class CommunicationAdmin(admin.ModelAdmin):
    readonly_fields = ('id',)
    list_display = ('id', 'comm_type', 'label', 'value', 'is_primary', 'employer_organization')
    list_filter = ('comm_type', 'is_primary')
    search_fields = ('label', 'value')


@admin.register(models.SocialProfile)
class SocialProfileAdmin(admin.ModelAdmin):
    readonly_fields = ('id',)
    list_display = ('id', 'platform', 'handle', 'url')
    list_filter = ('platform',)
    search_fields = ('platform', 'handle', 'url')
