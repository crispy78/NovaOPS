from __future__ import annotations

from django.views.generic import ListView

from audit.models import EventLog

from .usermgmt import StaffRequiredMixin


class AuditLogView(StaffRequiredMixin, ListView):
    """Staff-only audit event log viewer with basic filtering."""

    template_name = 'core/audit_log.html'
    context_object_name = 'events'
    paginate_by = 50

    def get_queryset(self):
        qs = EventLog.objects.select_related('actor').order_by('-created_at')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(action__icontains=q) | EventLog.objects.filter(
                entity_type__icontains=q
            ).select_related('actor')
            qs = EventLog.objects.filter(
                pk__in=[e.pk for e in qs]
            ).select_related('actor').order_by('-created_at')
        entity_type = self.request.GET.get('entity_type', '').strip()
        if entity_type:
            qs = qs.filter(entity_type=entity_type)
        actor = self.request.GET.get('actor', '').strip()
        if actor:
            qs = qs.filter(actor__email__icontains=actor)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        ctx['entity_type'] = self.request.GET.get('entity_type', '')
        ctx['actor'] = self.request.GET.get('actor', '')
        ctx['entity_types'] = (
            EventLog.objects.values_list('entity_type', flat=True)
            .distinct().order_by('entity_type')
        )
        return ctx
