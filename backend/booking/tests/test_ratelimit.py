from collections.abc import AsyncIterator
from datetime import date, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis

from app.cache import ResponseCache
from app.listings.models import Listing
from app.ratelimit import RateLimitedError, check_rate_limit
from app.settings import Settings
from tests.helpers import Headers, book


@pytest.fixture
async def unreachable_redis() -> AsyncIterator[Redis]:
    client = Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2)
    yield client
    await client.aclose()


async def test_requests_over_the_limit_are_refused(redis: Redis) -> None:
    for _ in range(3):
        await check_rate_limit(redis, "client-a", limit=3)

    with pytest.raises(RateLimitedError) as refused:
        await check_rate_limit(redis, "client-a", limit=3)
    await check_rate_limit(redis, "client-b", limit=3)  # every client has its own counter

    assert refused.value.headers is not None
    assert 1 <= int(refused.value.headers["Retry-After"]) <= 60


async def test_limiter_and_cache_skip_redis_when_it_is_down(unreachable_redis: Redis) -> None:
    await check_rate_limit(unreachable_redis, "client", limit=0)  # does not raise
    cache = ResponseCache(unreachable_redis)
    await cache.set("key", b"value", 30)

    assert await cache.get("key") is None


def test_limits_are_read_from_the_environment(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SEARCH_RATE_LIMIT", "30")

    loaded = Settings(
        database_url=settings.database_url,
        payment_provider_api_key="key",
        payment_webhook_secret="secret",
    )

    assert loaded.search_rate_limit == 30


class TestSearchLimit:
    @pytest.fixture
    def settings(self, settings: Settings) -> Settings:
        return settings.model_copy(update={"search_rate_limit": 3})

    async def test_client_gets_429_with_retry_after(self, client: AsyncClient) -> None:
        responses = [await client.get("/api/v1/listings") for _ in range(4)]

        assert [r.status_code for r in responses] == [200, 200, 200, 429]
        limited = responses[-1]
        assert limited.headers["content-type"] == "application/problem+json"
        assert limited.json()["code"] == "rate_limited"
        assert "Retry-After" in limited.headers


class TestBookingLimit:
    @pytest.fixture
    def settings(self, settings: Settings) -> Settings:
        return settings.model_copy(update={"booking_rate_limit": 2})

    async def test_writes_are_limited_per_user(
        self, client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date
    ) -> None:
        guest = auth(uuid4())
        statuses = [
            (
                await book(client, guest, priced_listing, next_monday + timedelta(days=7 * n))
            ).status_code
            for n in range(3)
        ]
        someone_else = await book(client, auth(uuid4()), priced_listing, next_monday)

        assert statuses == [201, 201, 429]
        assert someone_else.status_code == 409  # limited per user: refused for the dates only
