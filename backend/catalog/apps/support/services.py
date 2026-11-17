"""Support requests. Every change of a ticket goes through these functions.

Status shows whose turn it is: `open` waits for support, `answered` waits for the user.
"""

from functools import partial
from uuid import UUID

from django.db import transaction
from django.template.loader import render_to_string
from rest_framework import status

from apps.common.exceptions import DomainError
from apps.notifications.tasks import send_email
from apps.support.models import Message, Ticket, TicketStatus
from apps.users.models import User


class TicketClosedError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    code = "ticket_closed"


@transaction.atomic
def ticket_open(
    *, user: User, topic: str, subject: str, text: str, booking_id: UUID | None = None
) -> Ticket:
    ticket = Ticket.objects.create(user=user, topic=topic, subject=subject, booking_id=booking_id)
    Message.objects.create(ticket=ticket, author=user, text=text)
    return ticket


@transaction.atomic
def ticket_add_message(*, ticket: Ticket, user: User, text: str) -> Message:
    """The user writes again: the ticket goes back to support."""
    if ticket.status == TicketStatus.CLOSED:
        raise TicketClosedError("This request is closed. Please open a new one.")
    message = Message.objects.create(ticket=ticket, author=user, text=text)
    ticket.status = TicketStatus.OPEN
    ticket.save(update_fields=["status", "updated_at"])
    return message


@transaction.atomic
def ticket_answer(*, ticket: Ticket, staff: User, text: str) -> Message:
    """Support replies (from Django Admin); the user gets the reply by email."""
    message = Message.objects.create(ticket=ticket, author=staff, text=text, from_support=True)
    ticket.status = TicketStatus.ANSWERED
    ticket.save(update_fields=["status", "updated_at"])

    body = render_to_string("support/answer.txt", {"ticket": ticket, "message": message})
    subject = f"Reply to your request: {ticket.subject}"
    transaction.on_commit(partial(send_email.delay, ticket.user.email, subject, body))
    return message


def ticket_close(*, ticket: Ticket) -> Ticket:
    ticket.status = TicketStatus.CLOSED
    ticket.save(update_fields=["status", "updated_at"])
    return ticket
