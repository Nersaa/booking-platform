from django.contrib import admin
from django.http import HttpRequest

from apps.outbox.models import OutboxEvent


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    """Read-only view for debugging event delivery."""

    list_display = ("routing_key", "id", "created_at", "published_at")
    list_filter = ("routing_key", ("published_at", admin.EmptyFieldListFilter))
    search_fields = ("id",)
    readonly_fields = ("id", "routing_key", "payload", "created_at", "published_at")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: OutboxEvent | None = None) -> bool:
        return False
