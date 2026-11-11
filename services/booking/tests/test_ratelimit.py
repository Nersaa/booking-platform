import asyncio
from collections.abc import AsyncIterator
from datetime import date, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis

from app.cache import ResponseCache
from app.listings.models import Listing
from app.ratelimit import Rate, RateLimiter
from app.settings import Settings
from tests.helpers import Headers, book


@pytest.fixture
async def unreachable_redis() -> AsyncIterator[Redis]:
    client = Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2)
    yield client
    await client.aclose()


async def test_burst_then_one_request_per_interval(redis: Redis) -> None:
    limiter = RateLimiter(redis)
    rate = Rate(limit=3, period_seconds=1)  # one slot back every 333 ms

    burst = [await limiter.hit("k", rate) for _ in range(4)]
    await asyncio.sleep(0.4)
    after_refill = await limiter.hit("k", rate)

    assert [d.allowed for d in burst] == [True, True, True, False]
    assert [d.remaining for d in burst[:3]] == [2, 1, 0]
    assert burst[3].retry_after_seconds == 1
    assert after_refill.allowed


async def test_keys_have_separate_budgets(redis: Redis) -> None:
    limiter = RateLimiter(redis)
    rate = Rate(limit=1, period_seconds=60)

    assert (await limiter.hit("a", rate)).allowed
    assert not (await limiter.hit("a", rate)).allowed
    assert (await limiter.hit("b", rate)).allowed


async def test_limiter_and_cache_fail_open_without_redis(unreachable_redis: Redis) -> None:
    decision = await RateLimiter(unreachable_redis).hit("k", Rate(1, 60))
    cache = ResponseCache(unreachable_redis)
    await cache.set("key", b"value", 30)

    assert decision.allowed
    assert await cache.get("key") is None


@pytest.mark.parametrize(
    ("value", "rate"),
    [("60/minute", Rate(60, 60)), (" 5 / second ", Rate(5, 1)), ("1000/hour", Rate(1000, 3600))],
)
def test_rates_are_read_from_settings(value: str, rate: Rate) -> None:
    assert Rate.parse(value) == rate


def test_rates_are_read_from_the_environment(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SEARCH_RATE_LIMIT", "30/second")

    loaded = Settings(
        database_url=settings.database_url,
        payment_provider_api_key="key",
        payment_webhook_secret="secret",
    )

    assert loaded.search_rate_limit == Rate(30, 1)


def test_malformed_rate_settings_are_rejected(settings: Settings) -> None:
    with pytest.raises(ValueError, match="search_rate_limit"):
        Settings.model_validate({**settings.model_dump(), "search_rate_limit": "lots"})


class TestSearchLimit:
    @pytest.fixture
    def settings(self, settings: Settings) -> Settings:
        return settings.model_copy(update={"search_rate_limit": Rate(3, 60)})

    async def test_client_gets_429_with_retry_after(self, client: AsyncClient) -> None:
        responses = [await client.get("/api/v1/listings") for _ in range(4)]

        assert [r.status_code for r in responses] == [200, 200, 200, 429]
        limited = responses[-1]
        assert limited.headers["content-type"] == "application/problem+json"
        assert limited.json()["code"] == "rate_limited"
        assert 1 <= int(limited.headers["Retry-After"]) <= 20
        assert limited.headers["RateLimit-Limit"] == "3"


class TestBookingLimit:
    @pytest.fixture
    def settings(self, settings: Settings) -> Settings:
        return settings.model_copy(update={"booking_rate_limit": Rate(2, 60)})

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
