from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import redis.asyncio as redis
from redis.exceptions import RedisError

from src.config import CacheConfig
from src.logger import get_logger
from src.observability.metrics import record_cache_operation
from src.observability.tracing import set_current_span_attribute

logger = get_logger(__name__)

CacheReadStatus = Literal["hit", "miss", "error", "disabled"]


@dataclass(frozen=True)
class CacheRead:
    value: bytes | None
    status: CacheReadStatus


class RedisCache:
    def __init__(self, config: CacheConfig) -> None:
        self._config = config
        self._client: redis.Redis | None = None

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    async def start(self) -> None:
        if not self._config.enabled or self._client is not None:
            return
        self._client = redis.from_url(
            self._config.redis_url,
            decode_responses=False,
            socket_connect_timeout=self._config.socket_timeout_seconds,
            socket_timeout=self._config.socket_timeout_seconds,
            retry_on_timeout=False,
        )

    async def get(self, key: str, *, cache_name: str) -> CacheRead:
        if not self._config.enabled:
            set_current_span_attribute("cache.result", "disabled")
            return CacheRead(value=None, status="disabled")

        client = self._client
        if client is None:
            await self.start()
            client = self._client
        if client is None:
            set_current_span_attribute("cache.result", "disabled")
            return CacheRead(value=None, status="disabled")

        try:
            value = await client.get(key)
        except RedisError:
            record_cache_operation(cache_name, "get", "error")
            set_current_span_attribute("cache.result", "error")
            logger.warning("Redis cache read failed for cache=%s", cache_name)
            return CacheRead(value=None, status="error")

        return CacheRead(value=value, status="hit" if value is not None else "miss")

    async def set(
        self,
        key: str,
        value: bytes,
        *,
        ttl_seconds: int,
        cache_name: str,
    ) -> None:
        if not self._config.enabled:
            return
        if len(value) > self._config.max_value_bytes:
            record_cache_operation(cache_name, "set", "oversized")
            return

        client = self._client
        if client is None:
            await self.start()
            client = self._client
        if client is None:
            return

        try:
            await client.set(key, value, ex=ttl_seconds)
        except RedisError:
            record_cache_operation(cache_name, "set", "error")
            logger.warning("Redis cache write failed for cache=%s", cache_name)
            return
        record_cache_operation(cache_name, "set", "success")

    async def delete(self, *keys: str, cache_name: str) -> None:
        if not self._config.enabled:
            return
        if not keys:
            return

        client = self._client
        if client is None:
            await self.start()
            client = self._client
        if client is None:
            return

        try:
            await client.delete(*keys)
        except RedisError:
            record_cache_operation(cache_name, "invalidate", "error")
            logger.warning("Redis cache invalidation failed for cache=%s", cache_name)
            return
        record_cache_operation(cache_name, "invalidate", "success")

    async def aclose(self) -> None:
        if self._client is None:
            return
        try:
            await self._client.aclose()
        except RedisError:
            logger.warning("Redis cache client close failed")
        finally:
            self._client = None
