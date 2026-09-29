from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import anyio
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy.ext.asyncio import AsyncSession

from src.assistant.checkpoints import open_checkpointer
from src.assistant.contracts import EXECUTING_RUN_STATUSES
from src.assistant.repository import AssistantRepository
from src.db.unit_of_work import UnitOfWork
from src.errors import ErrorCode
from src.shared.errors import ConflictError

logger = logging.getLogger(__name__)


class CheckpointCleanup:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        checkpointer_factory: Callable[
            [], AbstractAsyncContextManager[AsyncPostgresSaver]
        ] = open_checkpointer,
    ) -> None:
        self._uow_factory = uow_factory
        self._checkpointer_factory = checkpointer_factory

    async def drain(self) -> None:
        try:
            for _ in range(100):
                with anyio.fail_after(10):
                    async with self._uow_factory() as uow:
                        if uow.session is None:
                            raise RuntimeError("UnitOfWork has not been entered")
                        repository = AssistantRepository(uow.session)
                        cleanup = await repository.next_checkpoint_cleanup()
                        if cleanup is None:
                            return
                        async with self._checkpointer_factory() as saver:
                            await saver.adelete_thread(str(cleanup.thread_id))
                        await repository.remove_checkpoint_cleanup(cleanup)
        except Exception as exc:
            # The committed queue survives failures, including a crash after deleting a thread.
            logger.error("assistant_checkpoint_cleanup_failed error_type=%s", type(exc).__name__)

    async def run(self) -> None:
        while True:
            await self.drain()
            await anyio.sleep(30)


class AssistantProjectDeletionHook:
    def __init__(self, cleanup: CheckpointCleanup) -> None:
        self._cleanup = cleanup

    async def prepare(self, session: AsyncSession, project_id: int) -> None:
        # The caller holds the project lock also used by assistant commands.
        repository = AssistantRepository(session)
        runs = await repository.project_runs(project_id)
        if any(run.status in EXECUTING_RUN_STATUSES for run in runs):
            raise ConflictError(ErrorCode.ASSISTANT_RUN_ACTIVE)
        repository.queue_checkpoint_cleanup([run.id for run in runs])

    async def cleanup(self) -> None:
        await self._cleanup.drain()
