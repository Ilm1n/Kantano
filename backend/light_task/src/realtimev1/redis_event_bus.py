from __future__ import annotations

import asyncio
from typing import Any, cast

import redis.asyncio as redis

from src.logger import get_logger
from src.realtimev1.event_bus import DeliveryConsumer, EventBus
from src.realtimev1.events import RealtimeDeliveryMessage
from src.realtimev1.serialization import (
    deserialize_delivery_message,
    serialize_delivery_message,
)

logger = get_logger("src.realtimev1.redis_bus")


class RedisEventBus(EventBus):
    def __init__(
        self,
        *,
        redis_url: str,
        channel: str,
    ):
        self._redis_url = redis_url
        self._channel = channel
        self._redis: redis.Redis | None = None
        self._pubsub: Any | None = None
        self._listener_task: asyncio.Task[None] | None = None
        self._consumer: DeliveryConsumer | None = None

    async def start(self, consumer: DeliveryConsumer) -> None:
        if self._listener_task and not self._listener_task.done():
            return

        self._consumer = consumer
        self._redis = redis.from_url(
            self._redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        await cast(Any, self._redis).ping()
        pubsub = cast(Any, self._redis).pubsub()
        await pubsub.subscribe(self._channel)
        self._pubsub = pubsub

        self._listener_task = asyncio.create_task(self._listen_loop())
        logger.info("Realtime Redis subscriber started on channel=%s", self._channel)

    async def stop(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

        if self._pubsub:
            await self._pubsub.unsubscribe(self._channel)
            await self._pubsub.aclose()
            self._pubsub = None

        if self._redis:
            await self._redis.aclose()
            self._redis = None

    async def publish(self, message: RealtimeDeliveryMessage) -> None:
        if not self._redis:
            self._redis = redis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
            )

        raw = serialize_delivery_message(message)
        await self._redis.publish(self._channel, raw)
        logger.info(
            "Realtime publish event_type=%s event_id=%s scope=%s project_id=%s user_targets=%s audience=%s",
            message.envelope.event_type,
            message.envelope.event_id,
            message.envelope.scope,
            message.project_id,
            len(message.user_ids),
            message.audience,
        )

    async def _listen_loop(self) -> None:
        if not self._pubsub:
            return

        while True:
            message = await self._pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1.0,
            )
            if not message:
                await asyncio.sleep(0.01)
                continue

            if message.get("type") != "message":
                continue

            if not self._consumer:
                continue

            raw_data = message.get("data")
            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode("utf-8")
            if not isinstance(raw_data, str):
                logger.warning("Realtime consume skipped: unsupported message payload")
                continue

            try:
                delivery = deserialize_delivery_message(raw_data)
            except Exception as exc:
                logger.exception("Realtime consume failed to decode message", exc_info=exc)
                continue

            logger.info(
                "Realtime consume event_type=%s event_id=%s scope=%s project_id=%s user_targets=%s audience=%s",
                delivery.envelope.event_type,
                delivery.envelope.event_id,
                delivery.envelope.scope,
                delivery.project_id,
                len(delivery.user_ids),
                delivery.audience,
            )

            try:
                await self._consumer(delivery)
            except Exception as exc:
                logger.exception(
                    "Realtime consumer failed for event_id=%s",
                    delivery.envelope.event_id,
                    exc_info=exc,
                )
