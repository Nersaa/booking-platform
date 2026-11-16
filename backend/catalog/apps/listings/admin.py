from collections.abc import Callable

from django import forms
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.db.models import QuerySet
from django.http import HttpRequest
from django.template.response import TemplateResponse
from django.utils.html import format_html

from apps.common import storage
from apps.common.exceptions import DomainError
from apps.listings import services
from apps.listings.models import Amenity, Listing, ListingPhoto, PhotoStatus


class RejectForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 4, "cols": 80}))


class ListingPhotoInline(admin.TabularInline):
    model = ListingPhoto
    extra = 0
    can_delete = False
    fields = ("preview", "status", "position", "width", "height")
    readonly_fields = fields

    @admin.display(description="Preview")
    def preview(self, photo: ListingPhoto) -> str:
        if photo.status != PhotoStatus.READY:
            return "-"
        return format_html('<img src="{}" height="80">', storage.public_url(photo.thumb_key))

    def has_add_permission(self, request: HttpRequest, obj: Listing | None = None) -> bool:
        return False


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    """Moderation desk. Status changes only through actions, so lifecycle rules always apply."""

    list_display = ("title", "host", "city", "property_type", "status", "created_at")
    list_filter = ("status", "property_type", "country")
    search_fields = ("title", "city", "host__email")
    list_select_related = ("host",)
    inlines = (ListingPhotoInline,)
    actions = ("publish_listings", "reject_listings")
    readonly_fields = (
        "host",
        "status",
        "rejection_reason",
        "published_at",
        "version",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    @admin.action(description="Publish selected listings", permissions=["change"])
    def publish_listings(self, request: HttpRequest, queryset: QuerySet[Listing]) -> None:
        self._apply(request, queryset, lambda listing: services.listing_publish(listing=listing))

    @admin.action(description="Reject selected listings", permissions=["change"])
    def reject_listings(
        self, request: HttpRequest, queryset: QuerySet[Listing]
    ) -> TemplateResponse | None:
        form = RejectForm(request.POST if "apply" in request.POST else None)
        if form.is_valid():
            reason = form.cleaned_data["reason"]
            self._apply(
                request,
                queryset,
                lambda listing: services.listing_reject(listing=listing, reason=reason),
            )
            return None
        context = {
            **self.admin_site.each_context(request),
            "title": "Reject listings",
            "listings": queryset,
            "form": form,
            "opts": self.model._meta,
            "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
        }
        return TemplateResponse(request, "admin/listings/listing/reject_listings.html", context)

    def _apply(
        self,
        request: HttpRequest,
        queryset: QuerySet[Listing],
        operation: Callable[[Listing], object],
    ) -> None:
        done = 0
        for listing in queryset:
            try:
                operation(listing)
            except DomainError as exc:
                self.message_user(request, f"{listing}: {exc}", level=messages.WARNING)
            else:
                done += 1
        if done:
            self.message_user(request, f"Updated {done} listing(s).", level=messages.SUCCESS)


@admin.register(Amenity)
class AmenityAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")
