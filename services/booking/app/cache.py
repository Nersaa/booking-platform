"""A small Redis cache for ready-made response bodies.

Failures are logged and treated as misses: without Redis the API is slower, not broken.
"""

import hashlib
import json
import logging
from typing import Any, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


def cache_key(namespace: str, params: dict[str, Any]) -> str:
    """Same parameters, same key, whatever their order."""
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    return f"{namespace}:{hashlib.sha256(canonical.encode()).hexdigest()}"


class ResponseCache:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get(self, key: str) -> bytes | None:
        try:
            # The client does not decode responses, so values come back as bytes.
            return cast(bytes | None, await self._redis.get(key))
        except RedisError as exc:
            logger.warning("Cache read failed for %s: %s", key, exc)
            return None

    async def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        try:
            await self._redis.set(key, value, ex=ttl_seconds)
        except RedisError as exc:
            logger.warning("Cache write failed for %s: %s", key, exc)
