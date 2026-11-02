import threading
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
from apps.outbox.services import (
    outbox_add,
    outbox_purge_published,
    outbox_relay_batch,
    outbox_relay_forever,
)

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


class StopAfter(threading.Event):
    """Stops the relay loop after a number of waits and records how long it waited."""

    def __init__(self, waits: int) -> None:
        super().__init__()
        self.remaining = waits
        self.waited: list[float] = []

    def wait(self, timeout: float | None = None) -> bool:
        self.waited.append(timeout or 0)
        self.remaining -= 1
        if self.remaining <= 0:
            self.set()
        return self.is_set()


@pytest.mark.django_db(transaction=True)  # the loop recycles DB connections
def test_relay_loop_drains_events_then_polls():
    add_events(3)
    publisher = FakePublisher()
    stop = StopAfter(waits=1)

    outbox_relay_forever(publisher=publisher, stop=stop, batch_size=2, poll_interval=0.5)

    assert len(publisher.sent) == 3  # full batch, then the rest without waiting
    assert stop.waited == [0.5]


@pytest.mark.django_db(transaction=True)  # the loop recycles DB connections
def test_relay_loop_backs_off_exponentially_while_broker_is_down():
    add_events(1)
    stop = StopAfter(waits=4)

    outbox_relay_forever(
        publisher=FakePublisher(fail_after=0), stop=stop, poll_interval=1, max_backoff=3
    )

    assert stop.waited == [1, 2, 3, 3]


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


def test_amqp_publisher_refuses_to_drop_unroutable_messages(rabbitmq_url):
    """Until a consumer has bound its queue, events must stay in the outbox."""
    publisher = AmqpPublisher(rabbitmq_url, EXCHANGE)
    try:
        with pytest.raises(PublishError, match="returned"):
            publisher.publish(routing_key="listing.nobody", body={}, message_id="1")
    finally:
        publisher.close()


def test_amqp_publisher_delivers_persistent_messages(rabbitmq_url):
    queue = Queue("test-listing-events", Exchange(EXCHANGE, type="topic"), routing_key="listing.*")
    with Connection(rabbitmq_url) as connection:
        queue(connection.default_channel).declare()

        publisher = AmqpPublisher(rabbitmq_url, EXCHANGE)
        try:
            publisher.publish(routing_key="listing.published", body={"a": 1}, message_id="42")
        finally:
            publisher.close()

        message = queue(connection.default_channel).get(no_ack=True)
    assert message is not None
    assert message.payload == {"a": 1}
    assert message.properties["message_id"] == "42"
    assert message.properties["delivery_mode"] == 2
