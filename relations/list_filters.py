"""Shared helpers for list views: organization trees, person ↔ org scoping."""

from __future__ import annotations

import uuid
from typing import Any

from django.http import HttpRequest, QueryDict


def querystring_excluding_page(request: HttpRequest, *, exclude: tuple[str, ...] = ('page',)) -> str:
    q = request.GET.copy()
    for key in exclude:
        q.pop(key, None)
    return q.urlencode()


def organization_descendant_ids(root_id: uuid.UUID) -> set[uuid.UUID]:
    """Return root_id plus all descendant organization IDs (breadth-first)."""
    from relations.models import Organization

    ids: set[uuid.UUID] = {root_id}
    frontier: list[uuid.UUID] = [root_id]
    while frontier:
        children = list(
            Organization.objects.filter(parent_id__in=frontier).values_list('id', flat=True),
        )
        ids.update(children)
        frontier = children
    return ids


def current_affiliation_org_ids_for_person(person_id: uuid.UUID) -> set[uuid.UUID]:
    from relations.models import Affiliation

    return set(
        Affiliation.objects.filter(person_id=person_id, end_date__isnull=True).values_list(
            'organization_id',
            flat=True,
        ),
    )


def resolve_sales_relation_org_ids(get_params: QueryDict | dict[str, Any]) -> frozenset[uuid.UUID] | None:
    """
    Combine optional account (org) and contact (person) filters for sales documents.

    Returns:
        None — no org/person filter (show all).
        frozenset() — impossible match (e.g. person not employed at selected subtree).
        non-empty frozenset — filter ``relation_organization_id__in=...`` (or prefixed lookup).
    """

    def _get(key: str) -> str:
        if isinstance(get_params, QueryDict):
            v = get_params.get(key, '')
        else:
            v = get_params.get(key) or ''
        return (v or '').strip()

    org_raw = _get('org')
    person_raw = _get('person')
    include_children = _get('include_children').lower() in ('1', 'true', 'on', 'yes')

    org_ids: set[uuid.UUID] | None = None

    if org_raw:
        try:
            root = uuid.UUID(str(org_raw))
        except (ValueError, TypeError):
            pass
        else:
            org_ids = organization_descendant_ids(root) if include_children else {root}

    if person_raw:
        try:
            pid = uuid.UUID(str(person_raw))
        except (ValueError, TypeError):
            pass
        else:
            p_orgs = current_affiliation_org_ids_for_person(pid)
            if org_ids is None:
                org_ids = set(p_orgs)
            else:
                org_ids &= p_orgs
            if not org_ids:
                return frozenset()

    if org_ids is None:
        return None
    return frozenset(org_ids)
