from __future__ import annotations

import uuid
from typing import Any

from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest

from .models import EventLog


def log_event(
    *,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str | None = None,
    actor=None,
    request: HttpRequest | None = None,
    metadata: dict[str, Any] | None = None,
) -> EventLog:
    """Persist an audit row. Prefer passing request so actor is inferred."""
    user = actor
    if user is None and request is not None and request.user.is_authenticated:
        user = request.user
    if isinstance(user, AnonymousUser):
        user = None

    eid = None
    if entity_id is not None:
        eid = entity_id if isinstance(entity_id, uuid.UUID) else uuid.UUID(str(entity_id))

    return EventLog.objects.create(
        actor=user,
        action=action,
        entity_type=entity_type,
        entity_id=eid,
        metadata=metadata or {},
    )
