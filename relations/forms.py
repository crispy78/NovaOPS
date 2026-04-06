from __future__ import annotations

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.forms import BaseModelFormSet, inlineformset_factory, modelformset_factory

from .models import (
    Address,
    Affiliation,
    Communication,
    Organization,
    OrganizationCategory,
    OrganizationCategoryTag,
    OrganizationUnitKind,
    Person,
    SocialProfile,
    SpecialEvent,
)


def _input_classes() -> str:
    return (
        'mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 '
        'shadow-sm focus:border-nova-500 focus:outline-none focus:ring-1 focus:ring-nova-500'
    )


def _checkbox_classes() -> str:
    return 'h-4 w-4 rounded border-slate-300 text-nova-600 focus:ring-nova-500'


class OrganizationForm(forms.ModelForm):
    categories = forms.ModelMultipleChoiceField(
        queryset=OrganizationCategoryTag.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text='Select one or more relationship categories.',
    )

    class Meta:
        model = Organization
        fields = (
            'parent',
            'unit_kind',
            'name',
            'legal_name',
            'primary_category',
            'categories',
            'industry',
            'tax_id_vat',
            'registration_number',
            'website',
            'notes',
            'is_archived',
        )
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 4, 'class': _input_classes()}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categories'].queryset = OrganizationCategoryTag.objects.order_by('label')
        self.fields['primary_category'].queryset = OrganizationCategoryTag.objects.order_by('label')

        if not self.instance.pk:
            parent = self.initial.get('parent') or self.data.get('parent')
            if parent:
                self.initial.setdefault('unit_kind', OrganizationUnitKind.DEPARTMENT)

        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault('class', _checkbox_classes())
            elif isinstance(field.widget, forms.CheckboxSelectMultiple):
                # style handled by template (checkboxes are intentionally minimal)
                pass
            else:
                field.widget.attrs.setdefault('class', _input_classes())

    def clean_categories(self):
        values = self.cleaned_data.get('categories') or OrganizationCategoryTag.objects.none()
        allowed = {c[0] for c in OrganizationCategory.choices}
        bad = [obj for obj in values if obj.code not in allowed]
        if bad:
            raise ValidationError('Invalid category selection.')
        return values


class PersonForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = (
            'title_prefix',
            'first_name',
            'last_name',
            'date_of_birth',
            'pronouns',
            'bio',
            'notes',
            'is_archived',
        )
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 4, 'class': _input_classes()}),
            'notes': forms.Textarea(attrs={'rows': 4, 'class': _input_classes()}),
            'date_of_birth': forms.DateInput(attrs={'type': 'date', 'class': _input_classes()}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault('class', _checkbox_classes())
            elif name not in self.Meta.widgets:
                field.widget.attrs.setdefault('class', _input_classes())


class AffiliationForm(forms.ModelForm):
    class Meta:
        model = Affiliation
        fields = ('organization', 'job_title', 'start_date', 'end_date', 'is_primary', 'notes')
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': _input_classes()}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': _input_classes()}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': _input_classes()}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name not in self.Meta.widgets:
                field.widget.attrs.setdefault('class', _input_classes())


AffiliationFormSet = inlineformset_factory(
    Person,
    Affiliation,
    form=AffiliationForm,
    extra=1,
    can_delete=True,
)


def _organization_ids_from_affiliation_post(data, prefix: str = 'aff') -> set[str]:
    """Read organization UUIDs from a submitted employment (affiliation) formset."""
    if not data:
        return set()
    try:
        n = int(data.get(f'{prefix}-TOTAL_FORMS', 0))
    except (TypeError, ValueError):
        return set()
    out: set[str] = set()
    for i in range(n):
        if data.get(f'{prefix}-{i}-DELETE') in ('on', 'true', '1', True):
            continue
        oid = (data.get(f'{prefix}-{i}-organization') or '').strip()
        if oid:
            out.add(oid)
    return out


class CommunicationForm(forms.ModelForm):
    class Meta:
        model = Communication
        fields = ('comm_type', 'label', 'value', 'is_primary', 'employer_organization')

    def __init__(self, *args, person=None, for_person: bool = True, **kwargs):
        self._person = person
        self.for_person = for_person
        super().__init__(*args, **kwargs)
        if not for_person:
            self.fields.pop('employer_organization', None)
        else:
            eo = self.fields['employer_organization']
            eo.required = False
            eo.empty_label = 'Personal / not tied to one employer'
            eo.widget.attrs.setdefault('class', _input_classes())
            if person and person.pk:
                person_ct = ContentType.objects.get_for_model(Person)
                ids = set(
                    Affiliation.objects.filter(person=person).values_list('organization_id', flat=True),
                )
                for c in Communication.objects.filter(content_type=person_ct, object_id=person.pk):
                    if c.employer_organization_id:
                        ids.add(c.employer_organization_id)
                if ids:
                    eo.queryset = Organization.objects.filter(pk__in=ids).order_by('name')
                else:
                    eo.queryset = Organization.objects.filter(is_archived=False).order_by('name')
            else:
                eo.queryset = Organization.objects.filter(is_archived=False).order_by('name')
        self.fields['comm_type'].widget.attrs.setdefault('class', _input_classes())
        self.fields['label'].widget.attrs.setdefault('class', _input_classes())
        self.fields['value'].widget.attrs.setdefault('class', _input_classes())
        self.fields['is_primary'].widget.attrs.setdefault('class', _checkbox_classes())

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('DELETE'):
            return cleaned
        if not self.for_person:
            return cleaned
        employer = cleaned.get('employer_organization')
        if not employer:
            return cleaned
        allowed = _organization_ids_from_affiliation_post(self.data or {})
        if str(employer.pk) in allowed:
            return cleaned
        person_id = None
        if self.instance.pk and self.instance.object_id:
            person_id = self.instance.object_id
        elif self._person and self._person.pk:
            person_id = self._person.pk
        if person_id and Affiliation.objects.filter(person_id=person_id, organization_id=employer.pk).exists():
            return cleaned
        raise ValidationError(
            {
                'employer_organization': (
                    'Add this organization under Employment first, then link the contact to that employer.'
                ),
            },
        )


class PersonCommunicationBaseFormSet(BaseModelFormSet):
    def __init__(self, *args, person=None, **kwargs):
        self.person = person
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        kwargs['person'] = self.person
        kwargs['for_person'] = True
        return super()._construct_form(i, **kwargs)


PersonCommunicationFormSet = modelformset_factory(
    Communication,
    form=CommunicationForm,
    formset=PersonCommunicationBaseFormSet,
    extra=1,
    can_delete=True,
)


class OrgCommunicationFormSet(BaseModelFormSet):
    def _construct_form(self, i, **kwargs):
        kwargs['for_person'] = False
        return super()._construct_form(i, **kwargs)


OrganizationCommunicationFormSet = modelformset_factory(
    Communication,
    form=CommunicationForm,
    formset=OrgCommunicationFormSet,
    extra=1,
    can_delete=True,
)


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ('address_type', 'label', 'street', 'street2', 'zipcode', 'city', 'state_province', 'country', 'is_primary')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, f in self.fields.items():
            if isinstance(f.widget, forms.CheckboxInput):
                f.widget.attrs.setdefault('class', _checkbox_classes())
            else:
                f.widget.attrs.setdefault('class', _input_classes())


AddressFormSet = modelformset_factory(
    Address,
    form=AddressForm,
    extra=1,
    can_delete=True,
)


class SocialProfileForm(forms.ModelForm):
    class Meta:
        model = SocialProfile
        fields = ('platform', 'handle', 'url')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs.setdefault('class', _input_classes())


SocialProfileFormSet = modelformset_factory(
    SocialProfile,
    form=SocialProfileForm,
    extra=1,
    can_delete=True,
)


class SpecialEventForm(forms.ModelForm):
    class Meta:
        model = SpecialEvent
        fields = ('name', 'event_date', 'notes')
        widgets = {
            'event_date': forms.DateInput(attrs={'type': 'date', 'class': _input_classes()}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': _input_classes()}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, f in self.fields.items():
            if name not in self.Meta.widgets:
                f.widget.attrs.setdefault('class', _input_classes())


SpecialEventFormSet = inlineformset_factory(
    Person,
    SpecialEvent,
    form=SpecialEventForm,
    extra=1,
    can_delete=True,
)

