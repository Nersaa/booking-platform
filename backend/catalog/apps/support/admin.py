"""Support desk: staff read requests and answer them right here in Django Admin."""

from typing import Any

from django import forms
from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.support import services
from apps.support.models import Message, Ticket, TicketStatus
from apps.users.models import User


class MessageInline(admin.TabularInline):
    """The conversation, oldest message first. Read-only: replies go through the form."""

    model = Message
    extra = 0
    can_delete = False
    fields = ("created_at", "sender", "text")
    readonly_fields = fields

    @admin.display(description="From")
    def sender(self, message: Message) -> str:
        return f"Support ({message.author.first_name})" if message.from_support else "User"

    def has_add_permission(self, request: HttpRequest, obj: Ticket | None = None) -> bool:
        return False


class TicketForm(forms.ModelForm):
    reply = forms.CharField(
        label="Your reply",
        required=False,
        widget=forms.Textarea(attrs={"rows": 5, "cols": 80}),
        help_text="Sent to the user by email. The request becomes 'Answered'.",
    )

    class Meta:
        model = Ticket
        fields: tuple[str, ...] = ()


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    form = TicketForm
    list_display = ("subject", "user", "topic", "status", "updated_at")
    list_filter = ("status", "topic")
    search_fields = ("subject", "user__email", "messages__text")
    list_select_related = ("user",)
    readonly_fields = ("user", "topic", "subject", "booking_id", "status", "created_at")
    fields = (*readonly_fields, "reply")
    inlines = (MessageInline,)
    actions = ("close_tickets",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False  # requests are opened by users on the website

    def save_model(self, request: HttpRequest, obj: Ticket, form: Any, change: bool) -> None:
        reply = form.cleaned_data.get("reply", "").strip()
        if not reply:
            return
        staff = request.user
        assert isinstance(staff, User)  # noqa: S101 - only staff users reach the admin
        services.ticket_answer(ticket=obj, staff=staff, text=reply)
        self.message_user(request, "Reply sent to the user.", level=messages.SUCCESS)

    @admin.action(description="Close selected requests", permissions=["change"])
    def close_tickets(self, request: HttpRequest, queryset: QuerySet[Ticket]) -> None:
        closed = 0
        for ticket in queryset.exclude(status=TicketStatus.CLOSED):
            services.ticket_close(ticket=ticket)
            closed += 1
        self.message_user(request, f"Closed {closed} request(s).", level=messages.SUCCESS)
