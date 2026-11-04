"""Rate limiting in Redis with GCRA, the token-bucket algorithm in a single key.

A limit of N per period lets a client burst up to N requests and then refills one slot
every period / N, so there is no window edge where 2N requests slip through. The check
and the update run in one Lua script, which keeps it atomic across API workers.

If Redis is unreachable the request is let through: limits protect the service, an
outage of the limiter must not take the service down.
"""

import logging
import math
import re
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.auth import Principal, current_principal
from app.errors import DomainError

logger = logging.getLogger(__name__)

PERIODS = {"second": 1, "minute": 60, "hour": 3600}
RATE_PATTERN = re.compile(r"^\s*(\d+)\s*/\s*(second|minute|hour)\s*$")

# KEYS[1]: bucket key. ARGV[1]: ms between requests at the steady rate. ARGV[2]: burst size.
# Stores the "theoretical arrival time" of the next request; returns
# {allowed, retry_after_ms, remaining}.
GCRA_SCRIPT = """
local now_parts = redis.call('TIME')
local now = tonumber(now_parts[1]) * 1000 + math.floor(tonumber(now_parts[2]) / 1000)
local interval = tonumber(ARGV[1])
local burst = tonumber(ARGV[2])
local tat = tonumber(redis.call('GET', KEYS[1])) or now
if tat < now then tat = now end
local new_tat = tat + interval
local allow_at = new_tat - interval * burst
if allow_at > now then
  return {0, allow_at - now, 0}
end
redis.call('SET', KEYS[1], new_tat, 'PX', new_tat - now)
return {1, 0, math.floor((now - allow_at) / interval)}
"""


@dataclass(frozen=True, slots=True)
class Rate:
    limit: int
    period_seconds: int

    @classmethod
    def parse(cls, value: object) -> object:
        """Accepts "60/minute"; anything else is left for the field validation to reject."""
        if isinstance(value, str) and (match := RATE_PATTERN.match(value)):
            return cls(int(match[1]), PERIODS[match[2]])
        return value

    @property
    def interval_ms(self) -> int:
        """Whole milliseconds keep the script in integers; rounding up errs on the strict side."""
        return math.ceil(self.period_seconds * 1000 / self.limit)


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    remaining: int
    retry_after_seconds: int


class RateLimitedError(DomainError):
    status_code = 429
    code = "rate_limited"

    def __init__(self, decision: Decision, rate: Rate) -> None:
        super().__init__("Too many requests. Retry later.")
        self.headers = {
            "Retry-After": str(decision.retry_after_seconds),
            "RateLimit-Limit": str(rate.limit),
            "RateLimit-Remaining": "0",
            "RateLimit-Reset": str(decision.retry_after_seconds),
        }


class RateLimiter:
    def __init__(self, redis: Redis) -> None:
        self._script = redis.register_script(GCRA_SCRIPT)

    async def hit(self, key: str, rate: Rate) -> Decision:
        try:
            allowed, retry_after_ms, remaining = await self._script(
                keys=[f"ratelimit:{key}"], args=[rate.interval_ms, rate.limit]
            )
        except RedisError as exc:
            logger.warning("Rate limiter unavailable, letting the request through: %s", exc)
            return Decision(allowed=True, remaining=rate.limit, retry_after_seconds=0)
        return Decision(
            allowed=bool(allowed),
            remaining=int(remaining),
            retry_after_seconds=math.ceil(int(retry_after_ms) / 1000),
        )


async def _enforce(request: Request, scope: str, identity: str) -> None:
    rate: Rate = getattr(request.app.state.settings, f"{scope}_rate_limit")
    limiter: RateLimiter = request.app.state.rate_limiter
    decision = await limiter.hit(f"{scope}:{identity}", rate)
    if not decision.allowed:
        raise RateLimitedError(decision, rate)


@dataclass(frozen=True, slots=True)
class LimitPerClient:
    """For anonymous endpoints. The client address comes from the gateway (X-Forwarded-For)."""

    scope: str

    async def __call__(self, request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        await _enforce(request, self.scope, f"ip:{client}")


@dataclass(frozen=True, slots=True)
class LimitPerUser:
    """For authenticated endpoints: the limit follows the account, not the address."""

    scope: str

    async def __call__(
        self, request: Request, principal: Annotated[Principal, Depends(current_principal)]
    ) -> None:
        await _enforce(request, self.scope, f"user:{principal.user_id}")
