"""Turns booking events from the Booking service into emails to guests and hosts.

Booking only knows user ids; contact details stay in Catalog.
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from contracts import BookingEvent, BookingEventType, BookingSnapshot
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string

from apps.listings.models import Listing
from apps.notifications.models import ProcessedEvent
from apps.notifications.tasks import send_email
from apps.users.models import User


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    body: str


def handle_booking_event(event: BookingEvent) -> bool:
    """Returns False if the event was already handled (a redelivery)."""
    try:
        with transaction.atomic():
            ProcessedEvent.objects.create(event_id=event.event_id, event_type=event.event_type)
            handler = HANDLERS.get(event.event_type)
            emails = handler(event.booking) if handler else []
            for email in emails:
                transaction.on_commit(
                    partial(send_email.delay, email.to, email.subject, email.body)
                )
    except IntegrityError:
        return False
    return True


def booking_confirmed_emails(booking: BookingSnapshot) -> list[Email]:
    return _emails(
        booking,
        guest_subject="Your stay at {title} is confirmed",
        host_subject="New booking at {title}",
        template="booking_confirmed",
    )


def booking_cancelled_emails(booking: BookingSnapshot) -> list[Email]:
    return _emails(
        booking,
        guest_subject="Your booking at {title} was cancelled",
        host_subject="Booking at {title} was cancelled",
        template="booking_cancelled",
    )


HANDLERS: dict[BookingEventType, Callable[[BookingSnapshot], list[Email]]] = {
    BookingEventType.CONFIRMED: booking_confirmed_emails,
    BookingEventType.CANCELLED: booking_cancelled_emails,
    # booking.completed will feed reviews (stage 4); no email for now.
}


def _emails(
    booking: BookingSnapshot, *, guest_subject: str, host_subject: str, template: str
) -> list[Email]:
    users = {u.id: u for u in User.objects.filter(id__in=[booking.guest_id, booking.host_id])}
    title = (
        Listing.objects.filter(id=booking.listing_id).values_list("title", flat=True).first()
        or "your listing"
    )
    context = {
        "booking": booking,
        "title": title,
        "nights": (booking.check_out - booking.check_in).days,
        "total": _money(booking.total, booking.currency),
        "refund": _money(booking.refund, booking.currency),
    }
    emails = []
    for role, user_id, subject in (
        ("guest", booking.guest_id, guest_subject),
        ("host", booking.host_id, host_subject),
    ):
        user = users.get(user_id)
        if user is None:
            continue
        body = render_to_string(f"notifications/{template}_{role}.txt", {**context, "user": user})
        emails.append(Email(to=user.email, subject=subject.format(title=title), body=body))
    return emails


def _money(minor_units: int, currency: str) -> str:
    return f"{minor_units / 100:,.2f} {currency}"
