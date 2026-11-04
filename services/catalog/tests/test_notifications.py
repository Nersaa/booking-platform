import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest
from contracts import BookingEvent, BookingEventType, BookingSnapshot, CancelledBy
from django.core import mail

from apps.notifications.consumer import BookingEventConsumer
from apps.notifications.models import ProcessedEvent
from apps.notifications.services import handle_booking_event
from apps.reviews.models import ReviewableStay
from tests.factories import HostFactory, ListingFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def stay():
    listing = ListingFactory(title="Loft & Garden", host=HostFactory(first_name="Hanna"))
    guest = UserFactory(first_name="Gil")
    return listing, guest


def event(listing, guest, event_type: BookingEventType, **fields: Any) -> BookingEvent:
    snapshot = {
        "id": uuid.uuid4(),
        "listing_id": listing.id,
        "guest_id": guest.id,
        "host_id": listing.host_id,
        "check_in": date(2030, 7, 1),
        "check_out": date(2030, 7, 4),
        "guests": 2,
        "currency": "EUR",
        "total": 32_500,
        **fields,
    }
    return BookingEvent(
        event_id=uuid.uuid4(),
        event_type=event_type,
        occurred_at=datetime.now(UTC),
        booking=BookingSnapshot(**snapshot),
    )


def test_confirmed_booking_emails_guest_and_host(stay, django_capture_on_commit_callbacks):
    listing, guest = stay

    with django_capture_on_commit_callbacks(execute=True):
        assert handle_booking_event(event(listing, guest, BookingEventType.CONFIRMED))

    to_guest, to_host = mail.outbox
    assert to_guest.to == [guest.email]
    assert to_guest.subject == "Your stay at Loft & Garden is confirmed"
    assert "Hi Gil" in to_guest.body
    assert "3 nights" in to_guest.body
    assert "325.00 EUR" in to_guest.body
    assert to_host.to == [listing.host.email]
    assert to_host.subject == "New booking at Loft & Garden"


def test_redelivered_event_sends_nothing_twice(stay, django_capture_on_commit_callbacks):
    listing, guest = stay
    confirmed = event(listing, guest, BookingEventType.CONFIRMED)

    with django_capture_on_commit_callbacks(execute=True):
        assert handle_booking_event(confirmed)
        assert not handle_booking_event(confirmed)

    assert len(mail.outbox) == 2
    assert ProcessedEvent.objects.count() == 1


@pytest.mark.parametrize(
    ("cancelled_by", "refund", "guest_line"),
    [
        (CancelledBy.GUEST, 16_250, "We are refunding 162.50 EUR"),
        (CancelledBy.GUEST, 0, "no refund is due"),
        (CancelledBy.HOST, 32_500, "was cancelled by the host"),
    ],
)
def test_cancellation_explains_the_refund(
    stay, django_capture_on_commit_callbacks, cancelled_by, refund, guest_line
):
    listing, guest = stay
    cancelled = event(
        listing, guest, BookingEventType.CANCELLED, cancelled_by=cancelled_by, refund=refund
    )

    with django_capture_on_commit_callbacks(execute=True):
        handle_booking_event(cancelled)

    to_guest, to_host = mail.outbox
    assert guest_line in to_guest.body
    assert "The dates are open again" in to_host.body


def test_completed_stay_opens_a_review_and_invites_only_the_guest(
    stay, django_capture_on_commit_callbacks
):
    listing, guest = stay
    completed = event(listing, guest, BookingEventType.COMPLETED)

    with django_capture_on_commit_callbacks(execute=True):
        assert handle_booking_event(completed)

    reviewable = ReviewableStay.objects.get()
    assert reviewable.booking_id == completed.booking.id
    assert reviewable.guest == guest
    assert reviewable.review_deadline == date(2030, 7, 18)
    [invitation] = mail.outbox
    assert invitation.to == [guest.email]
    assert invitation.subject == "How was your stay at Loft & Garden?"
    assert "until 18 Jul 2030" in invitation.body


class FakeMessage:
    def __init__(self) -> None:
        self.outcome: str | None = None

    def ack(self) -> None:
        self.outcome = "ack"

    def reject(self) -> None:
        self.outcome = "reject"

    def requeue(self) -> None:
        self.outcome = "requeue"


@pytest.mark.django_db(transaction=True)  # the consumer recycles DB connections
def test_consumer_acks_handled_events_and_rejects_garbage(stay):
    listing, guest = stay
    consumer = BookingEventConsumer(connection=None)
    good, bad = FakeMessage(), FakeMessage()

    consumer.on_message(
        event(listing, guest, BookingEventType.COMPLETED).model_dump(mode="json"), good
    )
    consumer.on_message({"event_type": "booking.confirmed"}, bad)

    assert good.outcome == "ack"
    assert bad.outcome == "reject"


@pytest.mark.django_db(transaction=True)
def test_consumer_requeues_when_handling_fails(stay, monkeypatch):
    listing, guest = stay
    consumer = BookingEventConsumer(connection=None)
    message = FakeMessage()

    def broken(_event):
        raise ConnectionError("database restarting")

    monkeypatch.setattr("apps.notifications.consumer.handle_booking_event", broken)
    consumer.on_message(
        event(listing, guest, BookingEventType.CONFIRMED).model_dump(mode="json"), message
    )

    assert message.outcome == "requeue"
