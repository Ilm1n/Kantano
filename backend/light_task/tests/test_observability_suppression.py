from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from opentelemetry.instrumentation.utils import is_instrumentation_enabled

from src.realtimev1.presence import PresenceService

pytestmark = pytest.mark.no_infra


@pytest.mark.asyncio
async def test_poll_suppression_does_not_cover_dispatch_or_commit(monkeypatch) -> None:
    from src.registration import outbox_publisher as publisher

    operations: list[tuple[str, bool]] = []

    async def scalars(query):
        operations.append(("select", is_instrumentation_enabled()))
        return SimpleNamespace(all=lambda: [object()])

    class Work:
        session = SimpleNamespace(scalars=scalars)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            operations.append(("commit", is_instrumentation_enabled()))

    async def dispatch(event):
        operations.append(("dispatch", is_instrumentation_enabled()))

    monkeypatch.setattr(publisher, "UnitOfWork", Work)
    monkeypatch.setattr(publisher, "_dispatch_outbox_event", dispatch)
    await publisher.publish_once()
    assert operations == [("select", False), ("dispatch", True), ("commit", True)]
    assert is_instrumentation_enabled()


@pytest.mark.asyncio
async def test_stats_query_suppressed_and_context_restored_on_failure(monkeypatch) -> None:
    from src.registration import outbox_publisher as publisher

    async def execute(query):
        assert not is_instrumentation_enabled()
        raise RuntimeError("database unavailable")

    class Session:
        async def __aenter__(self):
            return SimpleNamespace(execute=execute)

        async def __aexit__(self, *args):
            assert is_instrumentation_enabled()

    monkeypatch.setattr(publisher.db_helper, "async_session_maker", Session)
    with pytest.raises(RuntimeError, match="database unavailable"):
        await publisher.update_outbox_stats()
    assert is_instrumentation_enabled()


@pytest.mark.asyncio
async def test_presence_suppresses_only_heartbeat_and_background_scan(monkeypatch) -> None:
    service = PresenceService(redis_url="redis://localhost", key_prefix="a:b:c", ttl_seconds=30)
    operations: list[tuple[str, bool]] = []

    async def expire(*args):
        operations.append(("expire", is_instrumentation_enabled()))

    async def set_key(*args, **kwargs):
        operations.append(("set", is_instrumentation_enabled()))

    async def scan_iter(**kwargs):
        operations.append(("scan", is_instrumentation_enabled()))
        yield "a:b:c:1:2:viewing:3"

    client = SimpleNamespace(expire=expire, set=set_key, scan_iter=scan_iter)

    async def ensure(**kwargs):
        assert is_instrumentation_enabled(), "Reconnect probes must remain instrumented"
        return client

    monkeypatch.setattr(service, "_ensure_client", ensure)
    await service.mark(project_id=1, task_id=2, user_id=3, mode="viewing")
    await service.heartbeat(project_id=1, task_id=2, user_id=3, mode="viewing")
    initial = await service.snapshot(project_id=1)
    periodic = await service.snapshot(project_id=1, background=True)
    assert initial == periodic
    assert periodic[0].viewing_user_ids == [3]
    assert operations == [("set", True), ("expire", False), ("scan", True), ("scan", False)]

    async def broken_expire(*args):
        assert not is_instrumentation_enabled()
        raise RuntimeError("redis unavailable")

    client.expire = broken_expire
    unavailable = AsyncMock()
    monkeypatch.setattr(service, "_mark_unavailable", unavailable)
    await service.heartbeat(project_id=1, task_id=2, user_id=3, mode="viewing")
    unavailable.assert_awaited_once()
    assert is_instrumentation_enabled()
