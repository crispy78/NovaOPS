from __future__ import annotations

import uuid
from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Prefetch, Q
from django.shortcuts import redirect

from .list_filters import organization_descendant_ids, querystring_excluding_page
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import (
    AddressFormSet,
    AffiliationFormSet,
    OrganizationCommunicationFormSet,
    OrganizationForm,
    PersonCommunicationFormSet,
    SocialProfileFormSet,
    SpecialEventFormSet,
    PersonForm,
)
from .models import (
    Address,
    Affiliation,
    Communication,
    CommunicationType,
    Organization,
    OrganizationCategory,
    OrganizationCategoryTag,
    OrganizationUnitKind,
    Person,
    SpecialEvent,
    SocialProfile,
)


def _delete_formset_marked_instances(formset) -> None:
    """Delete rows with DELETE checked. ``BaseModelFormSet.deleted_objects`` is only set inside ``save()``."""
    for form in formset.deleted_forms:
        if form.instance.pk:
            form.instance.delete()


def _group_person_contacts_for_list(comms: list) -> list[tuple[Organization | None, list]]:
    """Split communications into Personal / shared (None) then one block per employer; all rows kept."""
    if not comms:
        return []

    def _sort_within(lst: list) -> list:
        type_order = {CommunicationType.EMAIL: 0, CommunicationType.PHONE: 1, CommunicationType.FAX: 2}

        def key(c):
            return (
                not c.is_primary,
                type_order.get(c.comm_type, 9),
                (c.label or '').lower(),
                c.value.lower(),
            )

        return sorted(lst, key=key)

    personal = [c for c in comms if not c.employer_organization_id]
    by_org: dict = defaultdict(list)
    for c in comms:
        if c.employer_organization_id:
            by_org[c.employer_organization].append(c)

    out: list[tuple[Organization | None, list]] = []
    if personal:
        out.append((None, _sort_within(personal)))
    for org in sorted(by_org.keys(), key=lambda o: o.name.lower()):
        out.append((org, _sort_within(by_org[org])))
    return out


def _person_contact_table_rows(
    person: Person,
    contact_overview_groups: list[tuple[Organization | None, list]],
) -> list[dict]:
    """Build one table row per current employer (+ orphan employer comms), then personal block last."""
    personal: list = []
    pending: dict = {}
    for org, items in contact_overview_groups:
        if org is None:
            personal = list(items)
        else:
            pending[org.id] = (org, list(items))

    rows: list[dict] = []

    affiliations = list(getattr(person, 'current_affiliations', []) or [])
    affiliations.sort(key=lambda a: (not a.is_primary, a.organization.name.lower()))
    seen_org: set = set()
    for aff in affiliations:
        oid = aff.organization_id
        if oid in seen_org:
            continue
        seen_org.add(oid)
        org = aff.organization
        pair = pending.pop(oid, None)
        comms = pair[1] if pair else []
        rows.append(
            {
                'org': org,
                'job_title': (aff.job_title or '').strip(),
                'contacts': comms,
                'aff_primary': bool(aff.is_primary),
            },
        )

    for _oid, (org, comms) in sorted(pending.items(), key=lambda x: x[1][0].name.lower()):
        rows.append(
            {'org': org, 'job_title': '', 'contacts': comms, 'aff_primary': False},
        )

    if personal:
        rows.append(
            {'org': None, 'job_title': '', 'contacts': personal, 'aff_primary': False},
        )

    if not rows:
        rows.append(
            {'org': None, 'job_title': '', 'contacts': [], 'aff_primary': False},
        )
    return rows


def _subtree_preorder_with_ids(*, root: Organization) -> tuple[list[tuple[Organization, int]], list]:
    """
    Root at depth 0, then children in DFS order (sorted by name per level).
    Returns (rows, ids) where ids is every organization id in the subtree (including root).
    """
    nodes = list(
        Organization.objects.only('id', 'parent_id', 'name', 'legal_name', 'unit_kind').order_by('name'),
    )
    by_parent: dict = {}
    for n in nodes:
        by_parent.setdefault(n.parent_id, []).append(n)

    rows: list[tuple[Organization, int]] = []

    def walk(o: Organization, depth: int) -> None:
        rows.append((o, depth))
        for c in by_parent.get(o.id, []):
            walk(c, depth + 1)

    walk(root, 0)
    ids = [o.id for o, _ in rows]
    return rows, ids


def _org_chart_nodes(
    *,
    request,
    root: Organization,
    preorder_rows: list[tuple[Organization, int]],
    org_ids: list[uuid.UUID],
    current_by_org: dict,
) -> list[dict[str, str]]:
    """
    Flat nodes for d3-org-chart (id / parentId). Organizations first, then people as children of their unit.
    """
    org_id_set = set(org_ids)
    nodes: list[dict[str, str]] = []

    for o, depth in preorder_rows:
        parent_id = ''
        if o.id != root.id and o.parent_id and o.parent_id in org_id_set:
            parent_id = str(o.parent_id)
        nodes.append(
            {
                'id': str(o.id),
                'parentId': parent_id,
                'name': o.name,
                'positionName': o.get_unit_kind_display(),
                'nodeType': 'organization',
                'profileUrl': request.build_absolute_uri(
                    reverse('relations:organization_detail', kwargs={'pk': o.pk}),
                ),
            },
        )

    for oid in org_ids:
        for aff in current_by_org.get(oid, []):
            nodes.append(
                {
                    'id': f'aff-{aff.id}',
                    'parentId': str(aff.organization_id),
                    'name': str(aff.person),
                    'positionName': (aff.job_title or 'Team member').strip() or 'Team member',
                    'nodeType': 'person',
                    'profileUrl': request.build_absolute_uri(
                        reverse('relations:person_detail', kwargs={'pk': aff.person.pk}),
                    ),
                },
            )

    return nodes


class OrganizationListView(LoginRequiredMixin, ListView):
    model = Organization
    template_name = 'relations/organization_list.html'
    context_object_name = 'organizations'
    paginate_by = 30

    def get_queryset(self):
        qs = Organization.objects.select_related('parent').prefetch_related('categories').order_by('name')
        q = (self.request.GET.get('q') or '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(legal_name__icontains=q))
        cat = (self.request.GET.get('cat') or '').strip().lower()
        allowed = {c[0] for c in OrganizationCategory.choices}
        if cat in allowed:
            qs = qs.filter(categories__code=cat).distinct()
        unit = (self.request.GET.get('unit') or '').strip().lower()
        unit_allowed = {c[0] for c in OrganizationUnitKind.choices}
        if unit in unit_allowed:
            qs = qs.filter(unit_kind=unit)
        # Default to showing active only; pass archived=all to see everything
        archived_param = self.request.GET.get('archived')
        archived = (archived_param if archived_param is not None else 'active').strip().lower()
        if archived in ('active', 'no'):
            qs = qs.filter(is_archived=False)
        elif archived in ('archived', 'yes'):
            qs = qs.filter(is_archived=True)
        # archived == 'all' → no filter
        parent_id = (self.request.GET.get('parent') or '').strip()
        if parent_id:
            try:
                uuid.UUID(str(parent_id))
            except ValueError:
                pass
            else:
                qs = qs.filter(parent_id=parent_id)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        cache = Organization.build_hierarchy_cache()
        ctx['org_breadcrumbs'] = {o.id: o.hierarchy_breadcrumb(cache=cache) for o in ctx['organizations']}
        ctx['organization_unit_kinds'] = OrganizationUnitKind.choices
        archived_param = self.request.GET.get('archived')
        ctx['filter_archived'] = (archived_param if archived_param is not None else 'active').strip().lower()
        ctx['filter_parent'] = (self.request.GET.get('parent') or '').strip()
        ctx['filter_parent_organizations'] = Organization.objects.filter(is_archived=False).order_by('name')
        ctx['filter_querystring'] = querystring_excluding_page(self.request)
        return ctx


class OrganizationCreateView(LoginRequiredMixin, CreateView):
    model = Organization
    form_class = OrganizationForm
    template_name = 'relations/organization_form.html'

    def get_initial(self):
        initial = super().get_initial()
        pid = (self.request.GET.get('parent') or '').strip()
        if pid:
            initial['parent'] = pid
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault('address_formset', AddressFormSet(prefix='addr', queryset=Address.objects.none()))
        ctx.setdefault(
            'communication_formset',
            OrganizationCommunicationFormSet(prefix='comm', queryset=Communication.objects.none()),
        )
        ctx.setdefault('social_formset', SocialProfileFormSet(prefix='soc', queryset=SocialProfile.objects.none()))
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        response = super().form_valid(form)
        org = self.object
        org_ct = ContentType.objects.get_for_model(Organization)

        addr_fs = AddressFormSet(self.request.POST, prefix='addr', queryset=Address.objects.none())
        comm_fs = OrganizationCommunicationFormSet(
            self.request.POST,
            prefix='comm',
            queryset=Communication.objects.none(),
        )
        soc_fs = SocialProfileFormSet(self.request.POST, prefix='soc', queryset=SocialProfile.objects.none())
        if not (addr_fs.is_valid() and comm_fs.is_valid() and soc_fs.is_valid()):
            return self.form_invalid(form)

        self._save_generic_formsets(
            content_type=org_ct,
            object_id=org.id,
            addr_fs=addr_fs,
            comm_fs=comm_fs,
            soc_fs=soc_fs,
        )
        messages.success(self.request, 'Organization created.')
        return response

    @staticmethod
    def _save_generic_formsets(*, content_type, object_id, addr_fs, comm_fs, soc_fs) -> None:
        # Addresses
        _delete_formset_marked_instances(addr_fs)
        for f in addr_fs.forms:
            if not f.cleaned_data or f.cleaned_data.get('DELETE'):
                continue
            a = f.save(commit=False)
            a.content_type = content_type
            a.object_id = object_id
            a.save()

        # Communications
        _delete_formset_marked_instances(comm_fs)
        for f in comm_fs.forms:
            if not f.cleaned_data or f.cleaned_data.get('DELETE'):
                continue
            c = f.save(commit=False)
            c.content_type = content_type
            c.object_id = object_id
            c.save()

        # Social profiles
        _delete_formset_marked_instances(soc_fs)
        for f in soc_fs.forms:
            if not f.cleaned_data or f.cleaned_data.get('DELETE'):
                continue
            s = f.save(commit=False)
            s.content_type = content_type
            s.object_id = object_id
            s.save()

    def get_success_url(self):
        return reverse('relations:organization_detail', kwargs={'pk': self.object.pk})


class OrganizationUpdateView(LoginRequiredMixin, UpdateView):
    model = Organization
    form_class = OrganizationForm
    template_name = 'relations/organization_form.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org: Organization = self.object
        org_ct = ContentType.objects.get_for_model(Organization)
        addr_qs = Address.objects.filter(content_type=org_ct, object_id=org.id)
        comm_qs = Communication.objects.filter(content_type=org_ct, object_id=org.id)
        soc_qs = SocialProfile.objects.filter(content_type=org_ct, object_id=org.id)
        ctx.setdefault('address_formset', AddressFormSet(prefix='addr', queryset=addr_qs))
        ctx.setdefault('communication_formset', OrganizationCommunicationFormSet(prefix='comm', queryset=comm_qs))
        ctx.setdefault('social_formset', SocialProfileFormSet(prefix='soc', queryset=soc_qs))
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        ctx = self.get_context_data()
        org_ct = ContentType.objects.get_for_model(Organization)
        addr_fs = AddressFormSet(self.request.POST, prefix='addr', queryset=ctx['address_formset'].queryset)
        comm_fs = OrganizationCommunicationFormSet(
            self.request.POST,
            prefix='comm',
            queryset=ctx['communication_formset'].queryset,
        )
        soc_fs = SocialProfileFormSet(self.request.POST, prefix='soc', queryset=ctx['social_formset'].queryset)
        if not (addr_fs.is_valid() and comm_fs.is_valid() and soc_fs.is_valid()):
            return self.render_to_response(
                self.get_context_data(
                    form=form,
                    address_formset=addr_fs,
                    communication_formset=comm_fs,
                    social_formset=soc_fs,
                )
            )

        response = super().form_valid(form)
        self._save_generic_formsets(
            content_type=org_ct,
            object_id=self.object.id,
            addr_fs=addr_fs,
            comm_fs=comm_fs,
            soc_fs=soc_fs,
        )
        messages.success(self.request, 'Organization saved.')
        return response

    def get_success_url(self):
        return reverse('relations:organization_detail', kwargs={'pk': self.object.pk})

    _save_generic_formsets = OrganizationCreateView._save_generic_formsets


class OrganizationDetailView(LoginRequiredMixin, DetailView):
    model = Organization
    template_name = 'relations/organization_detail.html'
    context_object_name = 'org'

    def get_queryset(self):
        return (
            Organization.objects.select_related('parent', 'primary_category')
            .prefetch_related('children', 'categories')
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org: Organization = ctx['org']
        ctx['org_hierarchy_breadcrumb'] = org.hierarchy_breadcrumb()

        org_ct = ContentType.objects.get_for_model(Organization)
        ctx['addresses'] = Address.objects.filter(content_type=org_ct, object_id=org.id).order_by(
            'address_type',
            'label',
            'city',
        )
        ctx['communications'] = Communication.objects.filter(content_type=org_ct, object_id=org.id).order_by(
            'comm_type',
            '-is_primary',
            'label',
        )
        ctx['social_profiles'] = SocialProfile.objects.filter(content_type=org_ct, object_id=org.id).order_by(
            'platform',
            'handle',
        )

        preorder_rows, org_ids = _subtree_preorder_with_ids(root=org)

        current_aff = (
            Affiliation.objects.select_related('person', 'organization')
            .filter(organization_id__in=org_ids, end_date__isnull=True)
            .order_by('person__last_name', 'person__first_name')
        )
        current_by_org: dict = {}
        for a in current_aff:
            current_by_org.setdefault(a.organization_id, []).append(a)

        ctx['org_chart_data'] = _org_chart_nodes(
            request=self.request,
            root=org,
            preorder_rows=preorder_rows,
            org_ids=org_ids,
            current_by_org=current_by_org,
        )
        past_aff = (
            Affiliation.objects.select_related('person', 'organization')
            .filter(organization_id__in=org_ids, end_date__isnull=False)
            .order_by('-end_date')
        )
        ctx['past_affiliations'] = past_aff
        show_cp = org.is_customer_or_prospect_relation()
        ctx['show_customer_assets_link'] = show_cp
        ctx['show_customer_mjop_link'] = show_cp
        return ctx


class PersonListView(LoginRequiredMixin, ListView):
    model = Person
    template_name = 'relations/person_list.html'
    context_object_name = 'people'
    paginate_by = 30

    def get_queryset(self):
        qs = Person.objects.prefetch_related(
            Prefetch(
                'affiliations',
                queryset=Affiliation.objects.select_related('organization').filter(
                    end_date__isnull=True,
                ).order_by('-is_primary', 'start_date'),
                to_attr='current_affiliations',
            ),
        ).order_by('last_name', 'first_name')
        g = self.request.GET
        org_id = (g.get('org') or '').strip()
        if org_id:
            try:
                root = uuid.UUID(str(org_id))
            except ValueError:
                org_id = ''
            else:
                include_children = g.get('include_children', '').lower() in ('1', 'true', 'on', 'yes')
                oids = organization_descendant_ids(root) if include_children else {root}
                qs = qs.filter(
                    affiliations__organization_id__in=oids,
                    affiliations__end_date__isnull=True,
                ).distinct()
        q = (g.get('q') or '').strip()
        if q:
            person_ct = ContentType.objects.get_for_model(Person)
            comm_person_ids = Communication.objects.filter(
                content_type=person_ct,
                comm_type__in=(
                    CommunicationType.EMAIL,
                    CommunicationType.PHONE,
                    CommunicationType.FAX,
                ),
                value__icontains=q,
            ).values_list('object_id', flat=True)
            qs = qs.filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(affiliations__organization__name__icontains=q)
                | Q(pk__in=comm_person_ids),
            ).distinct()
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        g = self.request.GET
        ctx['filter_org'] = (g.get('org') or '').strip()
        ctx['filter_include_children'] = g.get('include_children', '').lower() in ('1', 'true', 'on', 'yes')
        ctx['filter_organizations'] = Organization.objects.filter(is_archived=False).order_by('name')
        ctx['filter_querystring'] = querystring_excluding_page(self.request)

        people = ctx.get('people') or []
        if people:
            person_ct = ContentType.objects.get_for_model(Person)
            ids = [p.pk for p in people]
            comms = (
                Communication.objects.filter(
                    content_type=person_ct,
                    object_id__in=ids,
                    comm_type__in=(
                        CommunicationType.EMAIL,
                        CommunicationType.PHONE,
                        CommunicationType.FAX,
                    ),
                )
                .select_related('employer_organization')
                .order_by('object_id', 'employer_organization_id', '-is_primary', 'comm_type', 'label', 'value')
            )
            by_person: dict = defaultdict(list)
            for c in comms:
                by_person[c.object_id].append(c)
            for p in people:
                plist = by_person.get(p.pk, [])
                groups = _group_person_contacts_for_list(plist)
                p.contact_overview_groups = groups
                p.list_contact_rows = _person_contact_table_rows(p, groups)
        return ctx


class PersonCreateView(LoginRequiredMixin, CreateView):
    model = Person
    form_class = PersonForm
    template_name = 'relations/person_form.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault('affiliation_formset', AffiliationFormSet(prefix='aff'))
        ctx.setdefault(
            'communication_formset',
            PersonCommunicationFormSet(prefix='comm', queryset=Communication.objects.none(), person=None),
        )
        ctx.setdefault('special_event_formset', SpecialEventFormSet(prefix='sev'))
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        response = super().form_valid(form)
        person = self.object
        aff_fs = AffiliationFormSet(self.request.POST, instance=person, prefix='aff')
        if not aff_fs.is_valid():
            return self.render_to_response(
                self.get_context_data(
                    form=form,
                    affiliation_formset=aff_fs,
                    communication_formset=PersonCommunicationFormSet(
                        self.request.POST,
                        prefix='comm',
                        queryset=Communication.objects.none(),
                        person=person,
                    ),
                    special_event_formset=SpecialEventFormSet(self.request.POST, instance=person, prefix='sev'),
                ),
            )
        comm_fs = PersonCommunicationFormSet(
            self.request.POST,
            prefix='comm',
            queryset=Communication.objects.none(),
            person=person,
        )
        sev_fs = SpecialEventFormSet(self.request.POST, instance=person, prefix='sev')
        if not (comm_fs.is_valid() and sev_fs.is_valid()):
            return self.render_to_response(
                self.get_context_data(
                    form=form,
                    affiliation_formset=AffiliationFormSet(self.request.POST, instance=person, prefix='aff'),
                    communication_formset=comm_fs,
                    special_event_formset=sev_fs,
                ),
            )

        aff_fs.save()
        sev_fs.save()

        person_ct = ContentType.objects.get_for_model(Person)
        valid_employer_ids = set(
            Affiliation.objects.filter(person_id=person.id, end_date__isnull=True).values_list(
                'organization_id',
                flat=True,
            ),
        )
        for f in comm_fs.forms:
            if not f.cleaned_data or f.cleaned_data.get('DELETE'):
                continue
            comm = f.save(commit=False)
            comm.content_type = person_ct
            comm.object_id = person.id
            if comm.employer_organization_id and comm.employer_organization_id not in valid_employer_ids:
                comm.employer_organization = None
            comm.save()

        messages.success(self.request, 'Person created.')
        return response

    def get_success_url(self):
        return reverse('relations:person_detail', kwargs={'pk': self.object.pk})


class PersonUpdateView(LoginRequiredMixin, UpdateView):
    model = Person
    form_class = PersonForm
    template_name = 'relations/person_form.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        person: Person = self.object
        person_ct = ContentType.objects.get_for_model(Person)
        comm_qs = Communication.objects.filter(content_type=person_ct, object_id=person.id)
        ctx.setdefault('affiliation_formset', AffiliationFormSet(instance=person, prefix='aff'))
        ctx.setdefault(
            'communication_formset',
            PersonCommunicationFormSet(prefix='comm', queryset=comm_qs, person=person),
        )
        ctx.setdefault('special_event_formset', SpecialEventFormSet(instance=person, prefix='sev'))
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        ctx = self.get_context_data()
        aff_fs = AffiliationFormSet(self.request.POST, instance=self.object, prefix='aff')
        comm_fs = PersonCommunicationFormSet(
            self.request.POST,
            prefix='comm',
            queryset=ctx['communication_formset'].queryset,
            person=self.object,
        )
        sev_fs = SpecialEventFormSet(self.request.POST, instance=self.object, prefix='sev')
        if not aff_fs.is_valid():
            return self.render_to_response(
                self.get_context_data(
                    form=form,
                    affiliation_formset=aff_fs,
                    communication_formset=PersonCommunicationFormSet(
                        self.request.POST,
                        prefix='comm',
                        queryset=ctx['communication_formset'].queryset,
                        person=self.object,
                    ),
                    special_event_formset=SpecialEventFormSet(
                        self.request.POST,
                        instance=self.object,
                        prefix='sev',
                    ),
                ),
            )
        # Validate comms before saving affiliations: comm validation uses DB + POST; if we
        # save aff first, employer-linked contacts for the old org fail validation.
        if not (comm_fs.is_valid() and sev_fs.is_valid()):
            return self.render_to_response(
                self.get_context_data(
                    form=form,
                    affiliation_formset=aff_fs,
                    communication_formset=comm_fs,
                    special_event_formset=sev_fs,
                ),
            )

        response = super().form_valid(form)
        aff_fs.save()

        sev_fs.save()

        person_ct = ContentType.objects.get_for_model(Person)
        valid_employer_ids = set(
            Affiliation.objects.filter(person_id=self.object.id, end_date__isnull=True).values_list(
                'organization_id',
                flat=True,
            ),
        )
        stripped_employer = False
        _delete_formset_marked_instances(comm_fs)
        for f in comm_fs.forms:
            if not f.cleaned_data or f.cleaned_data.get('DELETE'):
                continue
            comm = f.save(commit=False)
            comm.content_type = person_ct
            comm.object_id = self.object.id
            if comm.employer_organization_id and comm.employer_organization_id not in valid_employer_ids:
                comm.employer_organization = None
                stripped_employer = True
            comm.save()

        messages.success(self.request, 'Person saved.')
        if stripped_employer:
            messages.info(
                self.request,
                'Contact methods that were tied to a previous employer were unlinked (set to personal) '
                'because that organization is no longer on the employment list.',
            )
        return response

    def get_success_url(self):
        return reverse('relations:person_detail', kwargs={'pk': self.object.pk})


class PersonDetailView(LoginRequiredMixin, DetailView):
    model = Person
    template_name = 'relations/person_detail.html'
    context_object_name = 'person'

    def get_queryset(self):
        return Person.objects.prefetch_related(
            Prefetch('affiliations', queryset=Affiliation.objects.select_related('organization').order_by('-start_date')),
            'special_events',
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        person: Person = ctx['person']
        person_ct = ContentType.objects.get_for_model(Person)
        comms = list(
            Communication.objects.filter(content_type=person_ct, object_id=person.id)
            .select_related('employer_organization')
            .order_by('comm_type', '-is_primary', 'label', 'value'),
        )

        # Split comms into personal vs. per-employer
        personal_comms = [c for c in comms if not c.employer_organization_id]
        by_org_id: dict = {}
        org_lookup: dict = {}
        for c in comms:
            if c.employer_organization_id:
                by_org_id.setdefault(c.employer_organization_id, []).append(c)
                org_lookup[c.employer_organization_id] = c.employer_organization

        # Build merged blocks: one per affiliation (grouped by org), then personal last.
        # Affiliations already ordered -start_date (current roles first).
        blocks: list[dict] = []
        seen_org_ids: set = set()
        for aff in person.affiliations.all():
            oid = aff.organization_id
            if oid in seen_org_ids:
                # Additional role at the same org - append to existing block
                for block in blocks:
                    if block['org'] and block['org'].pk == oid:
                        block['affiliations'].append(aff)
                        break
                continue
            seen_org_ids.add(oid)
            blocks.append({
                'org': aff.organization,
                'affiliations': [aff],
                'contacts': by_org_id.get(oid, []),
            })

        # Orgs that have contacts but no affiliation (edge case)
        for oid, org_comms in by_org_id.items():
            if oid not in seen_org_ids:
                blocks.append({
                    'org': org_lookup[oid],
                    'affiliations': [],
                    'contacts': org_comms,
                })

        # Personal block at the end
        if personal_comms:
            blocks.append({'org': None, 'affiliations': [], 'contacts': personal_comms})

        ctx['contact_blocks'] = blocks
        ctx['special_events'] = person.special_events.all()
        return ctx


