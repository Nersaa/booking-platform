from django.contrib import admin
from django.http import HttpRequest

from apps.reviews.models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    """Read-only: scores feed listing ratings, so they change only through the API."""

    list_display = ("listing", "author", "rating", "created_at")
    list_filter = ("rating",)
    search_fields = ("listing__title", "author__email", "text")
    readonly_fields = ("listing", "author", "stay", "rating", "text", "host_reply")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Review | None = None) -> bool:
        return False
