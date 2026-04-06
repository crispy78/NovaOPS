from django.contrib import admin

from .models import EventLog


@admin.register(EventLog)
class EventLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'action', 'entity_type', 'entity_id', 'actor')
    list_filter = ('action', 'entity_type', 'created_at')
    search_fields = ('action', 'entity_type')
    readonly_fields = ('id', 'actor', 'action', 'entity_type', 'entity_id', 'metadata', 'created_at')
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
