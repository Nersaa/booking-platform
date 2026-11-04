from decimal import Decimal

from contracts import ListingEventType, ListingSnapshot
from faststream.rabbit import RabbitBroker, TestRabbitBroker

from app.db import Database
from app.listings.consumer import CATALOG_EVENTS, register_listing_consumer
from app.listings.models import Listing
from app.listings.sync import apply_listing_snapshot
from tests.factories import listing_event, snapshot


async def _stored(db: Database, listing_id: object) -> Listing | None:
    async with db.sessions() as session:
        return await session.get(Listing, listing_id)


async def test_snapshot_is_inserted_then_updated_by_newer_version(db: Database) -> None:
    first = snapshot(version=2, title="Old title")
    newer = first.model_copy(update={"version": 3, "title": "New title"})

    async with db.sessions.begin() as session:
        assert await apply_listing_snapshot(session, first)
        assert await apply_listing_snapshot(session, newer)

    stored = await _stored(db, first.id)
    assert stored is not None
    assert (stored.version, stored.title) == (3, "New title")
    assert stored.amenities == ["wifi", "kitchen"]


async def test_stale_and_duplicate_snapshots_are_ignored(db: Database) -> None:
    current = snapshot(version=5, title="Current")

    async with db.sessions.begin() as session:
        await apply_listing_snapshot(session, current)
        assert not await apply_listing_snapshot(session, current)
        assert not await apply_listing_snapshot(
            session, current.model_copy(update={"version": 4, "title": "Stale"})
        )

    stored = await _stored(db, current.id)
    assert stored is not None
    assert (stored.version, stored.title) == (5, "Current")


async def test_rating_from_reviews_reaches_the_read_model(db: Database) -> None:
    unrated = snapshot(version=2)
    reviewed = unrated.model_copy(
        update={"version": 3, "rating": Decimal("4.67"), "review_count": 3}
    )

    async with db.sessions.begin() as session:
        await apply_listing_snapshot(session, unrated)
        await apply_listing_snapshot(session, reviewed)

    stored = await _stored(db, unrated.id)
    assert stored is not None
    assert (stored.rating, stored.review_count) == (Decimal("4.67"), 3)


def test_events_from_before_ratings_are_still_readable() -> None:
    old_payload = snapshot().model_dump(mode="json", exclude={"rating", "review_count"})

    parsed = ListingSnapshot.model_validate(old_payload)

    assert (parsed.rating, parsed.review_count) == (None, 0)


async def test_consumer_applies_events_from_the_catalog_exchange(db: Database) -> None:
    broker = RabbitBroker()
    register_listing_consumer(broker, db)
    published = snapshot(version=3)
    archived = published.model_copy(update={"version": 4, "is_listed": False})

    async with TestRabbitBroker(broker) as test_broker:
        for event in (
            listing_event(published),
            listing_event(archived, ListingEventType.ARCHIVED),
            listing_event(published),  # redelivered out of order
        ):
            await test_broker.publish(
                event.model_dump(mode="json"),
                exchange=CATALOG_EVENTS,
                routing_key=event.routing_key,
            )

    stored = await _stored(db, published.id)
    assert stored is not None
    assert stored.version == 4
    assert stored.is_listed is False
