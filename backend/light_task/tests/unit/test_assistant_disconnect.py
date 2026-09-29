from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import anyio
import anyio.lowlevel
import pytest
from starlette.requests import ClientDisconnect

from src.assistant import router

pytestmark = pytest.mark.no_infra


@pytest.mark.asyncio
@pytest.mark.parametrize("spec_version", ["2.3", "2.4"])
async def test_disconnect_finishes_cleanup_even_when_stream_is_cancelled(
    monkeypatch: pytest.MonkeyPatch, spec_version: str
) -> None:
    run_id = uuid4()
    cleaned: list[UUID] = []
    closed: list[bool] = []
    ready = anyio.Event()

    async def cleanup(actual_id: UUID) -> None:
        await anyio.lowlevel.checkpoint()
        cleaned.append(actual_id)

    async def stream() -> AsyncIterator[str]:
        try:
            yield "first event"
            await anyio.sleep_forever()
        finally:
            closed.append(True)

    async def receive() -> dict:
        await ready.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        if message["type"] == "http.response.body":
            ready.set()
            if spec_version == "2.4":
                raise OSError("Connection closed")

    monkeypatch.setattr(router, "interrupt_active_run", cleanup)
    response = router.AssistantStreamingResponse(stream(), run_id)
    if spec_version == "2.4":
        with pytest.raises(ClientDisconnect):
            await response({"type": "http", "asgi": {"spec_version": spec_version}}, receive, send)
    else:
        await response({"type": "http", "asgi": {"spec_version": spec_version}}, receive, send)
    assert cleaned == [run_id]
    assert closed == [True]


@pytest.mark.asyncio
async def test_external_response_cancellation_finishes_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleaned: list[UUID] = []
    ready = anyio.Event()
    run_id = uuid4()

    async def cleanup(actual_id: UUID) -> None:
        await anyio.lowlevel.checkpoint()
        cleaned.append(actual_id)

    async def stream() -> AsyncIterator[str]:
        ready.set()
        await anyio.sleep_forever()
        yield "unreachable"

    async def receive() -> dict:
        await anyio.sleep_forever()
        return {}

    async def send(message: dict) -> None:
        pass

    monkeypatch.setattr(router, "interrupt_active_run", cleanup)
    response = router.AssistantStreamingResponse(stream(), run_id)
    async with anyio.create_task_group() as group:
        group.start_soon(response, {"type": "http", "asgi": {"spec_version": "2.3"}}, receive, send)
        await ready.wait()
        group.cancel_scope.cancel()
    assert cleaned == [run_id]
