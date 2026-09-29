from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from uuid import UUID

import anyio
from fastapi.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from src.assistant.runtime import StreamEvent

logger = logging.getLogger(__name__)


async def encode_events(events: AsyncGenerator[StreamEvent, None]) -> AsyncGenerator[str, None]:
    try:
        async for event, data in events:
            yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
    finally:
        await events.aclose()


class AssistantStreamingResponse(StreamingResponse):
    def __init__(
        self,
        stream: AsyncGenerator[str, None],
        run_id: UUID,
        on_disconnect: Callable[[UUID], Awaitable[None]],
    ) -> None:
        super().__init__(
            stream,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )
        self.run_id = run_id
        self.stream = stream
        self._on_disconnect = on_disconnect

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.move_on_after(10, shield=True):
                try:
                    await self._on_disconnect(self.run_id)
                except Exception as exc:
                    logger.error(
                        "assistant_run_cleanup_failed run_id=%s error_type=%s",
                        self.run_id,
                        type(exc).__name__,
                    )
                finally:
                    await self.stream.aclose()
