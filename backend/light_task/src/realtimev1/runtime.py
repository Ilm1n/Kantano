from __future__ import annotations

import asyncio

from src.config import settings
from src.logger import get_logger
from src.projects.constants import ProjectRole
from src.realtimev1.connection_manager import ConnectionManager
from src.realtimev1.event_bus import EventBus
from src.realtimev1.events import (
    SYSTEM_ACTOR_USER_ID,
    RealtimeAudience,
    RealtimeDeliveryMessage,
    RealtimeEventType,
    RealtimeScope,
    new_event_envelope,
)
from src.realtimev1.presence import PresenceService
from src.realtimev1.redis_event_bus import RedisEventBus

logger = get_logger("src.realtimev1.runtime")


class RealtimeRuntime:
    def __init__(
        self,
        *,
        event_bus: EventBus,
        connection_manager: ConnectionManager,
        presence_service: PresenceService,
        presence_sync_interval_seconds: int,
    ):
        self._event_bus = event_bus
        self.connections = connection_manager
        self.presence = presence_service
        self._presence_sync_interval_seconds = presence_sync_interval_seconds
        self._presence_sync_task: asyncio.Task[None] | None = None
        self._event_bus_started = False

    async def start(self) -> None:
        try:
            await self._event_bus.start(self.consume)
            self._event_bus_started = True
        except Exception as exc:
            self._event_bus_started = False
            logger.exception(
                "Realtime bus start failed, runtime will continue in local-only dispatch mode",
                exc_info=exc,
            )

        await self.presence.start()
        if self.presence.is_available:
            self._presence_sync_task = asyncio.create_task(self._presence_sync_loop())
        logger.info("Realtime runtime started")

    async def stop(self) -> None:
        if self._presence_sync_task:
            self._presence_sync_task.cancel()
            try:
                await self._presence_sync_task
            except asyncio.CancelledError:
                pass
            self._presence_sync_task = None

        await self.presence.stop()
        if self._event_bus_started:
            await self._event_bus.stop()
            self._event_bus_started = False
        else:
            try:
                await self._event_bus.stop()
            except Exception:
                pass
        logger.info("Realtime runtime stopped")

    async def publish(self, message: RealtimeDeliveryMessage) -> None:
        try:
            await self._event_bus.publish(message)
        except Exception as exc:
            logger.exception(
                "Realtime publish failed, fallback to local dispatch",
                exc_info=exc,
            )
            await self.dispatch_local(message)

    async def dispatch_local(self, message: RealtimeDeliveryMessage) -> None:
        await self.consume(message)

    async def consume(self, message: RealtimeDeliveryMessage) -> None:
        await self.connections.dispatch(message)
        await self._apply_internal_side_effects(message)

    async def _apply_internal_side_effects(self, message: RealtimeDeliveryMessage) -> None:
        if message.project_id is None:
            return

        event_type = message.envelope.event_type
        payload = message.envelope.payload

        if event_type == RealtimeEventType.MEMBER_ROLE_CHANGED:
            user_id = payload.get("userId")
            role_value = payload.get("role")
            if isinstance(user_id, int) and isinstance(role_value, str):
                try:
                    role = ProjectRole(role_value)
                    await self.connections.update_role(
                        project_id=message.project_id,
                        user_id=user_id,
                        role=role,
                    )
                except ValueError:
                    pass

        if event_type == RealtimeEventType.MEMBER_REMOVED:
            user_id = payload.get("userId")
            if isinstance(user_id, int):
                await self.connections.close_project_user_connections(
                    project_id=message.project_id,
                    user_id=user_id,
                    reason="project_access_revoked",
                )
                await self._publish_project_presence_changed(
                    project_id=message.project_id,
                    actor_user_id=message.envelope.actor_user_id,
                )

        if event_type == RealtimeEventType.PROJECT_DELETED:
            await self.connections.close_project_connections(
                project_id=message.project_id,
                reason="project_deleted",
            )

    async def _publish_project_presence_changed(
        self,
        *,
        project_id: int,
        actor_user_id: int,
    ) -> None:
        active_user_count = await self.connections.active_project_user_count(
            project_id=project_id,
        )
        envelope = new_event_envelope(
            event_type=RealtimeEventType.PROJECT_PRESENCE_CHANGED,
            scope=RealtimeScope.PROJECT,
            project_id=project_id,
            actor_user_id=actor_user_id,
            payload={
                "projectId": project_id,
                "activeUserCount": active_user_count,
            },
        )
        await self.dispatch_local(
            RealtimeDeliveryMessage(
                envelope=envelope,
                project_id=project_id,
                audience=RealtimeAudience.ALL,
            )
        )

    async def _presence_sync_loop(self) -> None:
        while True:
            await asyncio.sleep(self._presence_sync_interval_seconds)
            if not self.presence.is_available:
                continue
            project_ids = await self.connections.active_project_ids()
            for project_id in project_ids:
                snapshot = await self.presence.snapshot(project_id=project_id)
                payload = {
                    "items": [
                        {
                            "taskId": item.task_id,
                            "viewingUserIds": item.viewing_user_ids,
                            "editingUserIds": item.editing_user_ids,
                        }
                        for item in snapshot
                    ]
                }
                envelope = new_event_envelope(
                    event_type=RealtimeEventType.TASK_PRESENCE_SYNC,
                    scope=RealtimeScope.PROJECT,
                    actor_user_id=SYSTEM_ACTOR_USER_ID,
                    payload=payload,
                    project_id=project_id,
                )
                await self.connections.dispatch(
                    RealtimeDeliveryMessage(
                        envelope=envelope,
                        project_id=project_id,
                        audience=RealtimeAudience.ALL,
                    )
                )


def build_realtime_runtime() -> RealtimeRuntime:
    event_bus = RedisEventBus(
        redis_url=settings.realtime.redis_url,
        channel=settings.realtime.redis_channel,
    )
    presence = PresenceService(
        redis_url=settings.realtime.redis_url,
        key_prefix=settings.realtime.presence_key_prefix,
        ttl_seconds=settings.realtime.presence_ttl_seconds,
    )
    return RealtimeRuntime(
        event_bus=event_bus,
        connection_manager=ConnectionManager(),
        presence_service=presence,
        presence_sync_interval_seconds=settings.realtime.presence_sync_interval_seconds,
    )
