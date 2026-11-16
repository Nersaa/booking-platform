"""Rate limiting with a counter per client and minute in Redis (fixed window).

Each request increments `ratelimit:<scope>:<client>:<minute>`; the key expires with its
minute. If Redis is unavailable the request is let through: the limiter protects the
service, it must not take it down.
"""

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.auth import Principal, current_principal
from app.errors import DomainError

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60


class RateLimitedError(DomainError):
    status_code = 429
    code = "rate_limited"

    def __init__(self, retry_after: int) -> None:
        super().__init__("Too many requests. Retry later.")
        self.headers = {"Retry-After": str(retry_after)}


async def check_rate_limit(redis: Redis, key: str, limit: int) -> None:
    now = int(time.time())
    counter = f"ratelimit:{key}:{now // WINDOW_SECONDS}"
    try:
        hits = await redis.incr(counter)
        if hits == 1:
            await redis.expire(counter, WINDOW_SECONDS)
    except RedisError as exc:
        logger.warning("Rate limiter unavailable, letting the request through: %s", exc)
        return
    if hits > limit:
        raise RateLimitedError(retry_after=WINDOW_SECONDS - now % WINDOW_SECONDS)


def _limit(request: Request, scope: str) -> int:
    limit: int = getattr(request.app.state.settings, f"{scope}_rate_limit")
    return limit


def limit_per_client(scope: str) -> Callable[[Request], Awaitable[None]]:
    """For anonymous endpoints. The client address comes from the gateway."""

    async def dependency(request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        await check_rate_limit(request.app.state.redis, f"{scope}:{client}", _limit(request, scope))

    return dependency


def limit_per_user(scope: str) -> Callable[..., Awaitable[None]]:
    """For authenticated endpoints: the limit follows the account, not the address."""

    async def dependency(
        request: Request, principal: Annotated[Principal, Depends(current_principal)]
    ) -> None:
        key = f"{scope}:{principal.user_id}"
        await check_rate_limit(request.app.state.redis, key, _limit(request, scope))

    return dependency
