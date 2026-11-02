from functools import cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = Field(description="postgresql+asyncpg://user:password@host/db")
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    jwks_url: str = "http://catalog-api:8000/.well-known/jwks.json"
    jwt_issuer: str = "catalog"
    jwt_audience: str = "booking-platform"
    jwks_cache_seconds: int = 3600

    log_level: str = "INFO"


@cache
def get_settings() -> Settings:
    return Settings()  # values come from the environment
