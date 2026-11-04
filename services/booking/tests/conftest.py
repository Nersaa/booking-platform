import os
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import jwt
import pytest
from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from jwt.algorithms import RSAAlgorithm
from redis.asyncio import Redis
from sqlalchemy import text

from app.auth import TokenVerifier
from app.cache import ResponseCache
from app.db import Database
from app.listings.models import Listing
from app.listings.sync import apply_listing_snapshot
from app.main import create_app
from app.ratelimit import Rate, RateLimiter
from app.settings import Settings
from tests.factories import PRICING, FakePaymentProvider, snapshot

ISSUER = "catalog"
AUDIENCE = "booking-platform"
KEY_ID = "test-key"
WEBHOOK_SECRET = "test-webhook-secret"
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"

TokenFactory = Callable[..., str]


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Real PostgreSQL with PostGIS: TEST_DATABASE_URL if set, else a throwaway container."""
    if url := os.environ.get("TEST_DATABASE_URL"):
        yield url
        return

    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgis/postgis:17-3.5-alpine", driver="asyncpg") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    """TEST_REDIS_URL if set, else a throwaway container."""
    if url := os.environ.get("TEST_REDIS_URL"):
        yield url
        return

    from testcontainers.community.redis import RedisContainer

    with RedisContainer("redis:7.4-alpine") as container:
        yield f"redis://{container.get_container_host_ip()}:{container.get_exposed_port(6379)}/0"


@pytest.fixture
async def redis(redis_url: str) -> AsyncIterator[Redis]:
    client = Redis.from_url(redis_url)
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture(scope="session")
def migrated_database_url(database_url: str) -> str:
    """Schema is built by the real migrations, so they are tested too."""
    config = Config(ALEMBIC_INI)
    config.attributes.update(database_url=database_url, configure_logger=False)
    command.upgrade(config, "head")
    return database_url


@pytest.fixture(scope="session")
async def database(migrated_database_url: str) -> AsyncIterator[Database]:
    db = Database(migrated_database_url)
    yield db
    await db.dispose()


@pytest.fixture
async def db(database: Database) -> AsyncIterator[Database]:
    yield database
    async with database.engine.begin() as connection:
        await connection.execute(
            text("TRUNCATE listings, outbox, idempotency_keys, processed_webhooks CASCADE")
        )


@pytest.fixture(scope="session")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class StaticKeyStore:
    def __init__(self, keys: dict[str, jwt.PyJWK]) -> None:
        self.keys = keys

    async def get(self, kid: str) -> jwt.PyJWK | None:
        return self.keys.get(kid)


def public_jwk(key: rsa.RSAPrivateKey, kid: str = KEY_ID) -> dict[str, Any]:
    jwk: dict[str, Any] = RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    return {**jwk, "kid": kid, "alg": "RS256", "use": "sig"}


@pytest.fixture
def verifier(signing_key: rsa.RSAPrivateKey) -> TokenVerifier:
    keys = StaticKeyStore({KEY_ID: jwt.PyJWK(public_jwk(signing_key))})
    return TokenVerifier(keys, issuer=ISSUER, audience=AUDIENCE)


@pytest.fixture
def make_token(signing_key: rsa.RSAPrivateKey) -> TokenFactory:
    """Tokens shaped exactly like the ones Catalog issues."""

    def make(
        user_id: UUID | None = None,
        roles: tuple[str, ...] = ("guest",),
        *,
        key: rsa.RSAPrivateKey | None = None,
        kid: str = KEY_ID,
        expires_in: int = 300,
        **claims: Any,
    ) -> str:
        now = datetime.now(UTC)
        payload = {
            "token_type": "access",
            "sub": str(user_id or uuid4()),
            "roles": list(roles),
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": now,
            "exp": now + timedelta(seconds=expires_in),
            "jti": uuid4().hex,
            **claims,
        }
        return jwt.encode(payload, key or signing_key, algorithm="RS256", headers={"kid": kid})

    return make


@pytest.fixture
def settings(migrated_database_url: str) -> Settings:
    """No caching and generous limits; the tests of those features override this."""
    unlimited = Rate(100_000, 60)
    return Settings(
        database_url=migrated_database_url,
        payment_provider_api_key="test-api-key",
        payment_webhook_secret=WEBHOOK_SECRET,
        search_cache_seconds=0,
        search_rate_limit=unlimited,
        public_rate_limit=unlimited,
        booking_rate_limit=unlimited,
    )


@pytest.fixture
async def client(
    db: Database,
    verifier: TokenVerifier,
    payment_provider: FakePaymentProvider,
    redis: Redis,
    settings: Settings,
) -> AsyncIterator[AsyncClient]:
    app = create_app(settings)
    app.state.db = db
    app.state.verifier = verifier
    app.state.payments = payment_provider
    app.state.cache = ResponseCache(redis)
    app.state.rate_limiter = RateLimiter(redis)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
def auth(make_token: TokenFactory) -> Callable[..., dict[str, str]]:
    def headers(user_id: UUID | None = None, *roles: str) -> dict[str, str]:
        token = make_token(user_id, roles or ("guest",))
        return {"Authorization": f"Bearer {token}"}

    return headers


@pytest.fixture
def make_listing(db: Database) -> Callable[..., Any]:
    """Puts a listing into the read model the same way the event consumer does."""

    async def make(**fields: Any) -> Listing:
        listing_snapshot = snapshot(**fields)
        async with db.sessions.begin() as session:
            await apply_listing_snapshot(session, listing_snapshot)
        async with db.sessions() as session:
            return await session.get_one(Listing, listing_snapshot.id)

    return make


@pytest.fixture
def payment_provider() -> FakePaymentProvider:
    return FakePaymentProvider()


@pytest.fixture
async def priced_listing(
    client: AsyncClient, make_listing: Callable[..., Any], auth: Callable[..., dict[str, str]]
) -> Listing:
    """A published listing for 3 guests with PRICING (EUR, min 2 nights)."""
    listing: Listing = await make_listing(max_guests=3)
    response = await client.put(
        f"/api/v1/host/listings/{listing.id}/pricing",
        json=PRICING,
        headers=auth(listing.host_id, "host"),
    )
    assert response.status_code == 200
    return listing


@pytest.fixture
def next_monday() -> date:
    """A Monday at least a week ahead, so weekday-dependent prices are deterministic."""
    today = datetime.now(UTC).date()
    return today + timedelta(days=7 + (7 - today.weekday()) % 7)
