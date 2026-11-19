"""HTTP API: `uvicorn app.main:create_app --factory`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import jwt
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from redis.asyncio import Redis

from app import health
from app.auth import TokenVerifier
from app.availability.router import host_router, public_router
from app.bookings.router import guest_router as bookings_router
from app.bookings.router import host_router as host_bookings_router
from app.cache import ResponseCache
from app.db import Database
from app.errors import register_error_handlers
from app.payments.provider import HttpPaymentProvider
from app.payments.router import router as payments_router
from app.search.router import router as search_router
from app.settings import Settings, get_settings
from app.stats.router import router as stats_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.db = Database(settings.database_url)
        payments = HttpPaymentProvider.build(
            settings.payment_provider_url, settings.payment_provider_api_key
        )
        app.state.payments = payments
        # Short timeouts: cache and limiter skip Redis when it fails, so it must fail fast.
        redis = Redis.from_url(settings.redis_url, socket_timeout=0.5, socket_connect_timeout=0.5)
        app.state.redis = redis
        app.state.cache = ResponseCache(redis)
        jwks = jwt.PyJWKClient(settings.jwks_url, lifespan=settings.jwks_cache_seconds, timeout=5)
        app.state.verifier = TokenVerifier(
            jwks, issuer=settings.jwt_issuer, audience=settings.jwt_audience
        )
        yield
        await payments.close()
        await redis.aclose()
        await app.state.db.dispose()

    app = FastAPI(
        title="Booking API",
        description=(
            "Search, availability, pricing and bookings. Amounts are in minor units (cents)."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs/booking/",
        openapi_url="/api/schema/booking/",
        redoc_url=None,
    )
    app.state.settings = settings
    register_error_handlers(app)
    # Request metrics on /metrics, scraped by Prometheus inside the Docker network.
    Instrumentator(excluded_handlers=["/metrics", "/healthz", "/readyz"]).instrument(app).expose(
        app, include_in_schema=False
    )
    app.include_router(health.router)
    app.include_router(search_router)
    app.include_router(public_router)
    app.include_router(host_router)
    app.include_router(bookings_router)
    app.include_router(host_bookings_router)
    app.include_router(stats_router)
    app.include_router(payments_router)
    return app
