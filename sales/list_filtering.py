"""List filter context and queryset helpers for sales documents."""

from __future__ import annotations

from typing import Any

from django.http import QueryDict

from relations.list_filters import querystring_excluding_page, resolve_sales_relation_org_ids
from relations.models import Organization, Person


def sales_list_filter_context(
    request,
    *,
    status_choices: list[tuple[str, str]],
    status_label: str = 'Status',
) -> dict[str, Any]:
    g = request.GET
    return {
        'filter_org': (g.get('org') or '').strip(),
        'filter_include_children': g.get('include_children', '').lower() in ('1', 'true', 'on', 'yes'),
        'filter_person': (g.get('person') or '').strip(),
        'filter_status': (g.get('status') or '').strip(),
        'filter_ref': (g.get('ref') or '').strip(),
        'filter_status_choices': status_choices,
        'filter_status_label': status_label,
        'filter_organizations': Organization.objects.filter(is_archived=False).order_by('name'),
        'filter_people': Person.objects.filter(is_archived=False).order_by('last_name', 'first_name'),
        'filter_querystring': querystring_excluding_page(request),
    }


def apply_relation_org_in(
    qs,
    get_params: QueryDict,
    *,
    field: str,
):
    """Filter queryset by relation org ids; ``field`` e.g. ``relation_organization_id``."""
    ids = resolve_sales_relation_org_ids(get_params)
    if ids is None:
        return qs
    if len(ids) == 0:
        return qs.none()
    return qs.filter(**{f'{field}__in': ids})


def apply_reference_icontains(qs, get_params: QueryDict, *, param: str = 'ref'):
    ref = (get_params.get(param) or '').strip()
    if ref:
        return qs.filter(reference__icontains=ref)
    return qs


def apply_status(qs, get_params: QueryDict, *, status_class: type, param: str = 'status'):
    allowed = {c[0] for c in status_class.choices}
    st = (get_params.get(param) or '').strip()
    if st in allowed:
        return qs.filter(status=st)
    return qs
