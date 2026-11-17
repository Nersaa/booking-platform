from functools import cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = Field(description="postgresql+asyncpg://user:password@host/db")
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    redis_url: str = "redis://localhost:6379/1"

    jwks_url: str = "http://catalog-api:8000/.well-known/jwks.json"
    jwt_issuer: str = "catalog"
    jwt_audience: str = "booking-platform"
    jwks_cache_seconds: int = 3600

    payment_provider_url: str = "http://payment-mock:8000"
    site_url: str = Field("http://localhost", description="The website, for links back to it.")
    payment_provider_api_key: str
    payment_webhook_secret: str
    hold_minutes: int = Field(15, description="How long unpaid bookings keep their dates.")

    search_cache_seconds: int = Field(30, ge=0, description="0 disables the search cache.")
    # Requests per minute: per client address for public reads, per user for booking writes.
    search_rate_limit: int = 60
    public_rate_limit: int = 120
    booking_rate_limit: int = 20

    log_level: str = "INFO"


@cache
def get_settings() -> Settings:
    return Settings()  # values come from the environment
