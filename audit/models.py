from django.conf import settings
from django.db import models

from core.models import UUIDPrimaryKeyModel


class EventLog(UUIDPrimaryKeyModel):
    """
    Append-only event stream (cart, quotes, orders, product edits, etc.).
    entity_id stores the UUID of the primary object the event refers to.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='audit_events',
    )
    action = models.CharField(max_length=80, db_index=True)
    entity_type = models.CharField(max_length=80, db_index=True)
    entity_id = models.UUIDField(null=True, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'event log entry'
        verbose_name_plural = 'event log'

    def __str__(self) -> str:
        return f'{self.created_at:%Y-%m-%d %H:%M} {self.action}'
