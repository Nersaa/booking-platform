import uuid

import pytest
from django.core import mail
from django.urls import reverse

from apps.support.models import Ticket, TicketStatus
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def open_ticket(client, **fields):
    body = {
        "topic": "booking",
        "subject": "Cannot check in",
        "text": "No keys at the door.",
        **fields,
    }
    return client.post(reverse("support-tickets"), body)


def test_user_opens_a_request_with_a_first_message(client_for):
    booking_id = uuid.uuid4()
    client = client_for(UserFactory(first_name="Gil"))

    response = open_ticket(client, booking_id=str(booking_id))

    assert response.status_code == 201
    assert response.data["status"] == "open"
    assert response.data["booking_id"] == str(booking_id)
    [message] = response.data["messages"]
    assert message["text"] == "No keys at the door."
    assert message["from_support"] is False
    assert message["author_name"] == "Gil"


def test_users_see_only_their_own_requests(client_for):
    owner, stranger = UserFactory(), UserFactory()
    ticket_id = open_ticket(client_for(owner)).data["id"]
    open_ticket(client_for(stranger), subject="Other question")

    listed = client_for(owner).get(reverse("support-tickets"))
    foreign = client_for(stranger).get(reverse("support-ticket", args=[ticket_id]))

    assert [t["id"] for t in listed.data["results"]] == [ticket_id]
    assert foreign.status_code == 404


def test_requests_need_a_login(api_client):
    assert open_ticket(api_client).status_code == 401


def test_support_answer_reaches_the_user_by_email(
    client_for, admin_client, django_capture_on_commit_callbacks
):
    user = UserFactory(first_name="Gil")
    ticket_id = open_ticket(client_for(user)).data["id"]
    change_url = reverse("admin:support_ticket_change", args=[ticket_id])

    first_message = Ticket.objects.get(pk=ticket_id).messages.get()
    # What the admin page posts: the reply plus the management data of the message list.
    form = {
        "reply": "The keys are in the key box, code 1234.",
        "messages-TOTAL_FORMS": "1",
        "messages-INITIAL_FORMS": "1",
        "messages-MIN_NUM_FORMS": "0",
        "messages-MAX_NUM_FORMS": "1000",
        "messages-0-id": str(first_message.id),
        "messages-0-ticket": ticket_id,
    }

    with django_capture_on_commit_callbacks(execute=True):
        response = admin_client.post(change_url, form)

    assert response.status_code == 302
    ticket = Ticket.objects.get(pk=ticket_id)
    assert ticket.status == TicketStatus.ANSWERED
    assert ticket.messages.last().from_support
    [email] = mail.outbox
    assert email.to == [user.email]
    assert email.subject == "Reply to your request: Cannot check in"
    assert "code 1234" in email.body


def test_a_new_message_returns_the_request_to_support(client_for):
    user = UserFactory()
    client = client_for(user)
    ticket_id = open_ticket(client).data["id"]
    Ticket.objects.filter(pk=ticket_id).update(status=TicketStatus.ANSWERED)

    response = client.post(
        reverse("support-ticket-messages", args=[ticket_id]), {"text": "Still no keys."}
    )

    assert response.status_code == 201
    assert Ticket.objects.get(pk=ticket_id).status == TicketStatus.OPEN


def test_closed_requests_take_no_more_messages(client_for):
    client = client_for(UserFactory())
    ticket_id = open_ticket(client).data["id"]

    closed = client.post(reverse("support-ticket-close", args=[ticket_id]))
    late = client.post(reverse("support-ticket-messages", args=[ticket_id]), {"text": "One more"})

    assert closed.data["status"] == "closed"
    assert late.status_code == 409
    assert late.data["code"] == "ticket_closed"


def test_support_desk_lists_and_closes_requests(client_for, admin_client):
    ticket_id = open_ticket(client_for(UserFactory())).data["id"]

    page = admin_client.get(reverse("admin:support_ticket_changelist"), {"status": "open"})
    admin_client.post(
        reverse("admin:support_ticket_changelist"),
        {"action": "close_tickets", "_selected_action": [ticket_id]},
    )

    assert b"Cannot check in" in page.content
    assert Ticket.objects.get(pk=ticket_id).status == TicketStatus.CLOSED
