"""HTTP API: `uvicorn app.main:create_app --factory`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app import health
from app.auth import JWKSKeyStore, TokenVerifier
from app.availability.router import host_router, public_router
from app.db import Database
from app.errors import register_error_handlers
from app.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.db = Database(settings.database_url)
        async with httpx.AsyncClient() as http:
            keys = JWKSKeyStore(settings.jwks_url, http, settings.jwks_cache_seconds)
            app.state.verifier = TokenVerifier(
                keys, issuer=settings.jwt_issuer, audience=settings.jwt_audience
            )
            yield
        await app.state.db.dispose()

    app = FastAPI(
        title="Booking API",
        description="Availability, pricing and bookings. Amounts are in minor units (cents).",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs/booking/",
        openapi_url="/api/schema/booking/",
        redoc_url=None,
    )
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(public_router)
    app.include_router(host_router)
    return app
