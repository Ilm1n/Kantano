from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from src.config import settings
from src.db.database import db_helper
from src.logger import get_logger
from src.projects.constants import ProjectRole
from src.realtimev1.auth import (
    WsAuthContext,
    WsAuthError,
    ensure_user_is_active,
    get_project_role,
    parse_auth_message,
    validate_access_token,
)
from src.realtimev1.dependencies import get_realtime_runtime_from_ws
from src.realtimev1.events import (
    RealtimeDeliveryMessage,
    RealtimeEventType,
    RealtimeScope,
    new_event_envelope,
)
from src.realtimev1.runtime import RealtimeRuntime

logger = get_logger("src.realtimev1.router")

router = APIRouter(tags=["Realtime"])


@router.websocket("/ws/user")
async def user_realtime_ws(
    websocket: WebSocket,
    runtime: Annotated[RealtimeRuntime, Depends(get_realtime_runtime_from_ws)],
) -> None:
    await websocket.accept()

    context: WsAuthContext | None = None
    expiry_task: asyncio.Task[None] | None = None
    try:
        context = await _authenticate_socket(websocket)
        async with db_helper.async_session_maker() as session:
            if not await ensure_user_is_active(session, user_id=context.user_id):
                raise WsAuthError("INACTIVE_USER")

        await runtime.connections.register_user(user_id=context.user_id, websocket=websocket)
        expiry_task = _spawn_expiry_task(websocket, context.expires_at)

        while True:
            message = await websocket.receive_json()
            if _is_ping(message):
                await websocket.send_json({"type": "pong"})
    except WsAuthError as exc:
        logger.warning("User ws auth failed: %s", str(exc))
        await _safe_close(websocket, reason=str(exc))
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("User ws failed", exc_info=exc)
        await _safe_close(websocket, reason="internal_error")
    finally:
        if expiry_task:
            expiry_task.cancel()
        await runtime.connections.unregister(websocket)


@router.websocket("/ws/projects/{project_id}")
async def project_realtime_ws(
    websocket: WebSocket,
    project_id: int,
    runtime: Annotated[RealtimeRuntime, Depends(get_realtime_runtime_from_ws)],
) -> None:
    await websocket.accept()

    context: WsAuthContext | None = None
    role: ProjectRole | None = None
    expiry_task: asyncio.Task[None] | None = None

    try:
        context = await _authenticate_socket(websocket)
        async with db_helper.async_session_maker() as session:
            if not await ensure_user_is_active(session, user_id=context.user_id):
                raise WsAuthError("INACTIVE_USER")

            raw_role = await get_project_role(
                session,
                project_id=project_id,
                user_id=context.user_id,
            )
            if raw_role is None:
                raise WsAuthError("PROJECT_ACCESS_DENIED")
            role = ProjectRole(raw_role)

        await runtime.connections.register_project(
            user_id=context.user_id,
            project_id=project_id,
            role=role,
            websocket=websocket,
        )
        expiry_task = _spawn_expiry_task(websocket, context.expires_at)
        await _send_project_presence_sync(
            websocket=websocket,
            runtime=runtime,
            project_id=project_id,
        )
        await _send_initial_presence_sync(
            websocket=websocket,
            runtime=runtime,
            project_id=project_id,
        )
        await _publish_project_presence_changed(
            runtime=runtime,
            project_id=project_id,
            actor_user_id=context.user_id,
            exclude_user_ids=[context.user_id],
        )

        while True:
            message = await websocket.receive_json()
            if _is_ping(message):
                await websocket.send_json({"type": "pong"})
                continue
            await _handle_project_message(
                websocket=websocket,
                message=message,
                runtime=runtime,
                context=context,
                project_id=project_id,
            )
    except WsAuthError as exc:
        logger.warning("Project ws auth failed: %s", str(exc))
        await _safe_close(websocket, reason=str(exc))
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("Project ws failed", exc_info=exc)
        await _safe_close(websocket, reason="internal_error")
    finally:
        if expiry_task:
            expiry_task.cancel()
        connection_context = await runtime.connections.unregister(websocket)
        if connection_context and connection_context.project_id is not None:
            await _cleanup_presence_on_disconnect(
                runtime=runtime,
                project_id=connection_context.project_id,
                user_id=connection_context.user_id,
                states=connection_context.presence_states,
            )
            await _publish_project_presence_changed(
                runtime=runtime,
                project_id=connection_context.project_id,
                actor_user_id=connection_context.user_id,
            )


async def _authenticate_socket(websocket: WebSocket) -> WsAuthContext:
    timeout = settings.realtime.ws_auth_timeout_seconds
    try:
        raw = await asyncio.wait_for(websocket.receive_json(), timeout=timeout)
    except TimeoutError as exc:
        raise WsAuthError("AUTH_TIMEOUT") from exc
    except Exception as exc:
        raise WsAuthError("AUTH_REQUIRED") from exc

    token = parse_auth_message(raw)
    return validate_access_token(token)


async def _handle_project_message(
    *,
    websocket: WebSocket,
    message: Any,
    runtime: RealtimeRuntime,
    context: WsAuthContext,
    project_id: int,
) -> None:
    if not isinstance(message, dict):
        return

    message_type = message.get("type")
    task_id = message.get("taskId")
    if not isinstance(task_id, int):
        return

    if message_type == RealtimeEventType.TASK_VIEWING_STARTED:
        await runtime.presence.mark(
            project_id=project_id,
            task_id=task_id,
            user_id=context.user_id,
            mode="viewing",
        )
        await runtime.connections.mark_presence(
            websocket,
            task_id=task_id,
            mode="viewing",
        )
        await _publish_presence_event(
            runtime=runtime,
            project_id=project_id,
            user_id=context.user_id,
            task_id=task_id,
            event_type=RealtimeEventType.TASK_VIEWING_STARTED,
        )
        return

    if message_type == RealtimeEventType.TASK_VIEWING_STOPPED:
        await runtime.presence.unmark(
            project_id=project_id,
            task_id=task_id,
            user_id=context.user_id,
            mode="viewing",
        )
        await runtime.connections.unmark_presence(
            websocket,
            task_id=task_id,
            mode="viewing",
        )
        await _publish_presence_event(
            runtime=runtime,
            project_id=project_id,
            user_id=context.user_id,
            task_id=task_id,
            event_type=RealtimeEventType.TASK_VIEWING_STOPPED,
        )
        return

    if message_type == RealtimeEventType.TASK_EDITING_STARTED:
        await runtime.presence.mark(
            project_id=project_id,
            task_id=task_id,
            user_id=context.user_id,
            mode="editing",
        )
        await runtime.connections.mark_presence(
            websocket,
            task_id=task_id,
            mode="editing",
        )
        await _publish_presence_event(
            runtime=runtime,
            project_id=project_id,
            user_id=context.user_id,
            task_id=task_id,
            event_type=RealtimeEventType.TASK_EDITING_STARTED,
        )
        return

    if message_type == RealtimeEventType.TASK_EDITING_STOPPED:
        await runtime.presence.unmark(
            project_id=project_id,
            task_id=task_id,
            user_id=context.user_id,
            mode="editing",
        )
        await runtime.connections.unmark_presence(
            websocket,
            task_id=task_id,
            mode="editing",
        )
        await _publish_presence_event(
            runtime=runtime,
            project_id=project_id,
            user_id=context.user_id,
            task_id=task_id,
            event_type=RealtimeEventType.TASK_EDITING_STOPPED,
        )
        return

    if message_type == "task.presence.heartbeat":
        mode = message.get("mode")
        if mode in {"viewing", "editing"}:
            await runtime.presence.heartbeat(
                project_id=project_id,
                task_id=task_id,
                user_id=context.user_id,
                mode=mode,
            )


async def _publish_presence_event(
    *,
    runtime: RealtimeRuntime,
    project_id: int,
    user_id: int,
    task_id: int,
    event_type: RealtimeEventType,
) -> None:
    envelope = new_event_envelope(
        event_type=event_type,
        scope=RealtimeScope.PROJECT,
        project_id=project_id,
        actor_user_id=user_id,
        payload={
            "taskId": task_id,
            "userId": user_id,
        },
    )
    await runtime.publish(
        RealtimeDeliveryMessage(
            envelope=envelope,
            project_id=project_id,
        )
    )


async def _send_project_presence_sync(
    *,
    websocket: WebSocket,
    runtime: RealtimeRuntime,
    project_id: int,
) -> None:
    active_user_count = await runtime.connections.active_project_user_count(
        project_id=project_id,
    )
    envelope = new_event_envelope(
        event_type=RealtimeEventType.PROJECT_PRESENCE_SYNC,
        scope=RealtimeScope.PROJECT,
        actor_user_id=0,
        project_id=project_id,
        payload={
            "projectId": project_id,
            "activeUserCount": active_user_count,
        },
    )
    await websocket.send_json(
        envelope.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
    )


async def _publish_project_presence_changed(
    *,
    runtime: RealtimeRuntime,
    project_id: int,
    actor_user_id: int,
    exclude_user_ids: list[int] | None = None,
) -> None:
    active_user_count = await runtime.connections.active_project_user_count(
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
    await runtime.dispatch_local(
        RealtimeDeliveryMessage(
            envelope=envelope,
            project_id=project_id,
            exclude_user_ids=exclude_user_ids or [],
        )
    )


async def _send_initial_presence_sync(
    *,
    websocket: WebSocket,
    runtime: RealtimeRuntime,
    project_id: int,
) -> None:
    snapshot = await runtime.presence.snapshot(project_id=project_id)
    envelope = new_event_envelope(
        event_type=RealtimeEventType.TASK_PRESENCE_SYNC,
        scope=RealtimeScope.PROJECT,
        actor_user_id=0,
        project_id=project_id,
        payload={
            "items": [
                {
                    "taskId": item.task_id,
                    "viewingUserIds": item.viewing_user_ids,
                    "editingUserIds": item.editing_user_ids,
                }
                for item in snapshot
            ]
        },
    )
    await websocket.send_json(
        envelope.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
    )


async def _cleanup_presence_on_disconnect(
    *,
    runtime: RealtimeRuntime,
    project_id: int,
    user_id: int,
    states: set[tuple[int, str]],
) -> None:
    for task_id, mode in states:
        await runtime.presence.unmark(
            project_id=project_id,
            task_id=task_id,
            user_id=user_id,
            mode=mode,
        )
        if mode == "viewing":
            event_type = RealtimeEventType.TASK_VIEWING_STOPPED
        else:
            event_type = RealtimeEventType.TASK_EDITING_STOPPED

        await _publish_presence_event(
            runtime=runtime,
            project_id=project_id,
            user_id=user_id,
            task_id=task_id,
            event_type=event_type,
        )


def _spawn_expiry_task(
    websocket: WebSocket, expires_at: datetime | None
) -> asyncio.Task[None] | None:
    if not expires_at:
        return None
    return asyncio.create_task(_close_at_expiry(websocket, expires_at))


async def _close_at_expiry(websocket: WebSocket, expires_at: datetime) -> None:
    delay = (expires_at - datetime.now(UTC)).total_seconds()
    if delay > 0:
        await asyncio.sleep(delay)
    await _safe_close(websocket, reason="TOKEN_EXPIRED")


async def _safe_close(websocket: WebSocket, *, reason: str) -> None:
    with contextlib.suppress(Exception):
        await websocket.close(code=1008, reason=reason)


def _is_ping(message: Any) -> bool:
    return isinstance(message, dict) and message.get("type") == "ping"
