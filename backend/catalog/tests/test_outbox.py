import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from django.db import transaction
from django.utils import timezone
from kombu import Connection, Exchange, Queue

from apps.outbox.models import OutboxEvent
from apps.outbox.publisher import AmqpPublisher, PublishError
from apps.outbox.services import outbox_add, outbox_purge_published, outbox_relay_batch
from apps.outbox.tasks import relay_outbox

EXCHANGE = "test.events"


class FakePublisher:
    def __init__(self, fail_after: int | None = None) -> None:
        self.sent: list[tuple[str, dict[str, Any], str]] = []
        self.fail_after = fail_after

    def publish(self, *, routing_key: str, body: dict[str, Any], message_id: str) -> None:
        if self.fail_after is not None and len(self.sent) >= self.fail_after:
            raise PublishError("broker is down")
        self.sent.append((routing_key, body, message_id))


def add_events(count: int) -> list[OutboxEvent]:
    with transaction.atomic():
        return [
            outbox_add(event_id=uuid.uuid4(), routing_key="listing.updated", payload={"n": n})
            for n in range(count)
        ]


@pytest.mark.django_db
def test_relay_publishes_pending_events_in_order_and_marks_them():
    added = add_events(3)
    publisher = FakePublisher()

    assert outbox_relay_batch(publisher=publisher) == 3
    assert outbox_relay_batch(publisher=publisher) == 0

    assert [message_id for *_, message_id in publisher.sent] == [str(e.id) for e in added]
    assert not OutboxEvent.objects.filter(published_at__isnull=True).exists()


@pytest.mark.django_db
def test_relay_keeps_what_failed_for_the_next_attempt():
    add_events(3)

    assert outbox_relay_batch(publisher=FakePublisher(fail_after=2)) == 2
    assert OutboxEvent.objects.filter(published_at__isnull=True).count() == 1

    with pytest.raises(PublishError):
        outbox_relay_batch(publisher=FakePublisher(fail_after=0))
    assert OutboxEvent.objects.filter(published_at__isnull=True).count() == 1


@pytest.mark.django_db
def test_relay_respects_batch_size():
    add_events(5)

    assert outbox_relay_batch(publisher=FakePublisher(), batch_size=2) == 2


@pytest.mark.django_db
def test_relay_task_publishes_pending_events(monkeypatch):
    add_events(2)
    publisher = FakePublisher()

    class FakeAmqpPublisher:
        def __init__(self, url, exchange):
            pass

        def __enter__(self):
            return publisher

        def __exit__(self, *exc_info):
            pass

    monkeypatch.setattr("apps.outbox.tasks.AmqpPublisher", FakeAmqpPublisher)

    assert relay_outbox() == 2
    assert relay_outbox() == 0  # nothing pending: no connection to the broker at all


@pytest.mark.django_db
def test_purge_removes_only_old_published_events():
    old, recent, pending = add_events(3)
    OutboxEvent.objects.filter(pk=old.pk).update(published_at=timezone.now() - timedelta(days=8))
    OutboxEvent.objects.filter(pk=recent.pk).update(published_at=timezone.now())

    assert outbox_purge_published() == 1
    assert set(OutboxEvent.objects.values_list("pk", flat=True)) == {recent.pk, pending.pk}


@pytest.fixture(scope="module")
def rabbitmq_url() -> Iterator[str]:
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.wait_strategies import LogMessageWaitStrategy

    container = (
        DockerContainer("rabbitmq:4.1-alpine")
        .with_exposed_ports(5672)
        .waiting_for(LogMessageWaitStrategy("Server startup complete"))
    )
    with container:
        host, port = container.get_container_host_ip(), container.get_exposed_port(5672)
        yield f"amqp://guest:guest@{host}:{port}//"


def test_amqp_publisher_delivers_persistent_messages(rabbitmq_url):
    queue = Queue("test-listing-events", Exchange(EXCHANGE, type="topic"), routing_key="listing.*")
    with Connection(rabbitmq_url) as connection:
        queue(connection.default_channel).declare()

        with AmqpPublisher(rabbitmq_url, EXCHANGE) as publisher:
            publisher.publish(routing_key="listing.published", body={"a": 1}, message_id="42")

        message = queue(connection.default_channel).get(no_ack=True)
    assert message is not None
    assert message.payload == {"a": 1}
    assert message.properties["message_id"] == "42"
    assert message.properties["delivery_mode"] == 2
