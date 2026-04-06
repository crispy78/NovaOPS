from __future__ import annotations

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from core.models import UUIDPrimaryKeyModel
from django.core.exceptions import ValidationError


class OrganizationCategory(models.TextChoices):
    CUSTOMER = 'customer', 'Customer'
    PROSPECT = 'prospect', 'Prospect'
    SUPPLIER = 'supplier', 'Supplier / vendor'
    PARTNER = 'partner', 'Partner'
    STRATEGIC = 'strategic', 'Strategic / VIP'
    INTERNAL = 'internal', 'Internal'


class OrganizationUnitKind(models.TextChoices):
    LEGAL_ENTITY = 'legal_entity', 'Legal entity / company'
    DEPARTMENT = 'department', 'Department'
    BRANCH = 'branch', 'Branch / site / office'
    TEAM = 'team', 'Team'
    OTHER = 'other', 'Other'


class OrganizationCategoryTag(UUIDPrimaryKeyModel):
    code = models.CharField(max_length=30, unique=True, db_index=True)
    label = models.CharField(max_length=120)

    class Meta:
        ordering = ['label']
        verbose_name = 'organization category'
        verbose_name_plural = 'organization categories'

    def __str__(self) -> str:
        return self.label


class Organization(UUIDPrimaryKeyModel):
    """
    One hierarchical concept that can represent:
    parent company → subsidiary → business unit → department.
    """

    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='children',
        verbose_name='parent organization',
    )
    unit_kind = models.CharField(
        max_length=32,
        choices=OrganizationUnitKind.choices,
        default=OrganizationUnitKind.LEGAL_ENTITY,
        db_index=True,
        help_text='What this row represents (company vs department, branch, etc.).',
    )
    name = models.CharField(max_length=255, db_index=True)
    legal_name = models.CharField(max_length=255, blank=True)
    primary_category = models.ForeignKey(
        OrganizationCategoryTag,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='organizations_primary',
        verbose_name='category',
        help_text='Primary relationship category (customer, prospect, supplier, partner, etc.).',
    )
    categories = models.ManyToManyField(
        OrganizationCategoryTag,
        blank=True,
        related_name='organizations',
        verbose_name='categories',
    )
    industry = models.CharField(max_length=200, blank=True, verbose_name='industry / sector')
    tax_id_vat = models.CharField(max_length=80, blank=True, verbose_name='tax ID / VAT number')
    registration_number = models.CharField(
        max_length=80,
        blank=True,
        verbose_name='registration / chamber of commerce number',
    )
    website = models.URLField(max_length=500, blank=True, verbose_name='website')
    notes = models.TextField(blank=True)

    is_archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'organization'
        verbose_name_plural = 'organizations'
        permissions = [
            ('archive_organization', 'Can archive/unarchive organizations (soft delete)'),
        ]

    def __str__(self) -> str:
        return self.name

    def category_labels(self) -> list[str]:
        return [c.label for c in self.categories.order_by('label')]

    def category_pairs(self) -> list[tuple[str, str]]:
        return list(self.categories.order_by('label').values_list('code', 'label'))

    @classmethod
    def build_hierarchy_cache(cls) -> dict:
        """id -> (parent_id, name) for breadcrumb paths without N+1 queries."""
        return {
            pk: (parent_id, name)
            for pk, parent_id, name in cls.objects.values_list('id', 'parent_id', 'name')
        }

    def hierarchy_breadcrumb(self, cache: dict | None = None) -> str:
        """Root-to-node path, e.g. 'Stadium Events Group › IT Department'."""
        cache = cache or type(self).build_hierarchy_cache()
        parts: list[str] = []
        oid = self.id
        seen: set = set()
        while oid and oid not in seen:
            seen.add(oid)
            row = cache.get(oid)
            if row is None:
                break
            parent_id, name = row
            parts.append(name)
            oid = parent_id
        return ' › '.join(reversed(parts))

    def is_customer_or_prospect_relation(self) -> bool:
        """True if primary or any tag category is customer or prospect (for quoting)."""
        codes = set(self.categories.values_list('code', flat=True))
        if self.primary_category_id:
            codes.add(self.primary_category.code)
        return bool(codes & {OrganizationCategory.CUSTOMER, OrganizationCategory.PROSPECT})

    def clean(self) -> None:
        super().clean()
        if self.parent_id and self.parent_id == self.id:
            raise ValidationError('An organization cannot be its own parent.')


class Person(UUIDPrimaryKeyModel):
    title_prefix = models.CharField(max_length=40, blank=True, verbose_name='title / prefix')
    first_name = models.CharField(max_length=120, db_index=True)
    last_name = models.CharField(max_length=120, db_index=True)
    date_of_birth = models.DateField(null=True, blank=True)
    pronouns = models.CharField(max_length=60, blank=True, verbose_name='gender / pronouns')
    bio = models.TextField(blank=True, verbose_name='background / bio')
    notes = models.TextField(blank=True)

    is_archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['last_name', 'first_name']
        verbose_name = 'person'
        verbose_name_plural = 'people'
        permissions = [
            ('archive_person', 'Can archive/unarchive people (soft delete)'),
        ]

    def __str__(self) -> str:
        return f'{self.first_name} {self.last_name}'.strip()


class Affiliation(UUIDPrimaryKeyModel):
    """Employment/role timeline linking a person to an organization."""

    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='affiliations')
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name='affiliations')
    job_title = models.CharField(max_length=200, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_primary = models.BooleanField(default=False, verbose_name='primary role')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-start_date', '-end_date']
        verbose_name = 'affiliation'
        verbose_name_plural = 'affiliations'
        indexes = [
            models.Index(fields=['person', 'end_date']),
            models.Index(fields=['organization', 'end_date']),
        ]

    def __str__(self) -> str:
        return f'{self.person} @ {self.organization}'


class OrganizationLinkType(UUIDPrimaryKeyModel):
    """Configurable lateral relationship types between organizations."""

    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'organization link type'
        verbose_name_plural = 'organization link types'

    def __str__(self) -> str:
        return self.name


class OrganizationLink(UUIDPrimaryKeyModel):
    """Lateral organization-to-organization relationships (outside the hierarchy)."""

    from_organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='links_from',
    )
    to_organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='links_to',
    )
    link_type = models.ForeignKey(OrganizationLinkType, on_delete=models.PROTECT)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['from_organization', 'link_type', 'to_organization']
        verbose_name = 'organization link'
        verbose_name_plural = 'organization links'
        constraints = [
            models.UniqueConstraint(
                fields=['from_organization', 'to_organization', 'link_type'],
                name='relations_unique_org_link_triple',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.from_organization} — {self.link_type} → {self.to_organization}'


class AddressType(models.TextChoices):
    BILLING = 'billing', 'Billing'
    SHIPPING = 'shipping', 'Shipping'
    VISITING = 'visiting', 'Visiting'
    HOME = 'home', 'Home'
    POSTAL = 'postal', 'Postal'
    OTHER = 'other', 'Other'


class Address(UUIDPrimaryKeyModel):
    """Generic address attachable to Person or Organization."""

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField(db_index=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    address_type = models.CharField(max_length=20, choices=AddressType, default=AddressType.OTHER)
    label = models.CharField(max_length=120, blank=True)
    street = models.CharField(max_length=255, blank=True, verbose_name='street address 1')
    street2 = models.CharField(max_length=255, blank=True, verbose_name='street address 2')
    city = models.CharField(max_length=120, blank=True)
    state_province = models.CharField(max_length=120, blank=True, verbose_name='state / province')
    zipcode = models.CharField(max_length=40, blank=True)
    country = models.CharField(max_length=120, blank=True)
    is_primary = models.BooleanField(default=False, verbose_name='primary')

    class Meta:
        ordering = ['address_type', 'label', 'city']
        verbose_name = 'address'
        verbose_name_plural = 'addresses'
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self) -> str:
        return self.label or f'{self.get_address_type_display()} address'


class CommunicationType(models.TextChoices):
    PHONE = 'phone', 'Phone'
    EMAIL = 'email', 'Email'
    FAX = 'fax', 'Fax'


class Communication(UUIDPrimaryKeyModel):
    """Generic communication detail attachable to Person or Organization."""

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField(db_index=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    comm_type = models.CharField(max_length=10, choices=CommunicationType)
    label = models.CharField(max_length=120, blank=True)
    value = models.CharField(max_length=255)
    is_primary = models.BooleanField(default=False)
    employer_organization = models.ForeignKey(
        'Organization',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='person_communications_at_employer',
        verbose_name='linked employer',
        help_text='For a person: which company this email/phone is for. Leave empty for personal or shared contact.',
    )

    class Meta:
        ordering = ['comm_type', '-is_primary', 'label', 'value']
        verbose_name = 'communication'
        verbose_name_plural = 'communications'
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['employer_organization']),
        ]

    def clean(self) -> None:
        super().clean()
        org_ct = ContentType.objects.get_for_model(Organization)
        person_ct = ContentType.objects.get_for_model(Person)
        if self.content_type_id == org_ct.id:
            if self.employer_organization_id:
                raise ValidationError(
                    {'employer_organization': 'Not used when the contact belongs to an organization record.'},
                )
            return
        if self.content_type_id != person_ct.id:
            return
        if self.employer_organization_id and self.object_id:
            if not Affiliation.objects.filter(
                person_id=self.object_id,
                organization_id=self.employer_organization_id,
            ).exists():
                raise ValidationError(
                    {
                        'employer_organization': 'This person must have an employment record for the selected organization.',
                    },
                )

    def __str__(self) -> str:
        return f'{self.get_comm_type_display()}: {self.value}'


class SocialProfile(UUIDPrimaryKeyModel):
    """Generic social profile attachable to Person or Organization."""

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField(db_index=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    platform = models.CharField(max_length=120)  # e.g. LinkedIn, X
    url = models.URLField(max_length=500, blank=True)
    handle = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['platform', 'handle']
        verbose_name = 'social profile'
        verbose_name_plural = 'social profiles'
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self) -> str:
        return f'{self.platform}: {self.handle or self.url}'


class SpecialEvent(UUIDPrimaryKeyModel):
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='special_events')
    name = models.CharField(max_length=200, verbose_name='event name / type')
    event_date = models.DateField(null=True, blank=True, verbose_name='event date')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['event_date', 'name']
        verbose_name = 'special event'
        verbose_name_plural = 'special events'

    def __str__(self) -> str:
        return self.name
