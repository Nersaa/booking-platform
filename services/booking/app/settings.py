from functools import cache
from typing import Annotated

from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, NoDecode

from app.ratelimit import Rate

# NoDecode: the environment holds "60/minute", not JSON.
RateSetting = Annotated[Rate, NoDecode, BeforeValidator(Rate.parse)]


class Settings(BaseSettings):
    database_url: str = Field(description="postgresql+asyncpg://user:password@host/db")
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    redis_url: str = "redis://localhost:6379/1"

    jwks_url: str = "http://catalog-api:8000/.well-known/jwks.json"
    jwt_issuer: str = "catalog"
    jwt_audience: str = "booking-platform"
    jwks_cache_seconds: int = 3600

    payment_provider_url: str = "http://payment-mock:8000"
    payment_provider_api_key: str
    payment_webhook_secret: str
    hold_minutes: int = Field(15, description="How long unpaid bookings keep their dates.")

    search_cache_seconds: int = Field(30, ge=0, description="0 disables the search cache.")
    # "<requests>/<second|minute|hour>"; per client IP for public reads, per user for writes.
    search_rate_limit: RateSetting = Rate(60, 60)
    public_rate_limit: RateSetting = Rate(120, 60)
    booking_rate_limit: RateSetting = Rate(20, 60)

    log_level: str = "INFO"
    metrics_port: int = Field(9100, description="Worker metrics for Prometheus.")


@cache
def get_settings() -> Settings:
    return Settings()  # values come from the environment
