from __future__ import annotations

import hashlib
from collections.abc import Iterable

import redis.asyncio as redis

from src.config import RegistrationConfig


class RegistrationRateLimiter:
    def __init__(self, client: redis.Redis, config: RegistrationConfig) -> None:
        self._client = client
        self._config = config

    async def allow(self, *, email: str, client_ip: str) -> int | None:
        email_key = self._email_key(email)
        cooldown_key = f"registration:cooldown:{email_key}"
        if not await self._set_if_absent(
            cooldown_key,
            self._config.resend_cooldown_seconds,
        ):
            return self._config.resend_cooldown_seconds

        limits: Iterable[tuple[str, int, int]] = (
            (f"registration:email:{email_key}", self._config.max_emails_per_hour, 3600),
            (
                f"registration:ip:{self._hash(client_ip)}",
                self._config.max_requests_per_ip_hour,
                3600,
            ),
        )
        for key, maximum, ttl in limits:
            count = await self._client.incr(key)
            if count == 1:
                await self._client.expire(key, ttl)
            if count > maximum:
                return max(int(await self._client.ttl(key)), 1)
        return None

    async def _set_if_absent(self, key: str, ttl: int) -> bool:
        return bool(await self._client.set(key, "1", ex=ttl, nx=True))

    @staticmethod
    def _email_key(email: str) -> str:
        return RegistrationRateLimiter._hash(email)

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()
