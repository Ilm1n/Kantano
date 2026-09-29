from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from sqlalchemy import func, select
from test_create_task_slice import _create_project, _register_and_login

from src.assistant import graph as graph_module
from src.assistant.checkpoints import open_checkpointer, setup_checkpointer
from src.assistant.cleanup import AssistantProjectDeletionHook, CheckpointCleanup
from src.assistant.dto import ConversationScope, DecideActionCommand, StartRunCommand
from src.assistant.models import AssistantCheckpointCleanup, AssistantConversation
from src.assistant.provider import ModelAnswer
from src.assistant.repository import AssistantRepository
from src.assistant.use_cases import (
    AssistantRunLifecycle,
    DecideActionUseCase,
    DeleteConversationUseCase,
    StartRunUseCase,
)
from src.config import settings
from src.db.database import db_helper
from src.db.unit_of_work import UnitOfWork
from src.errors import ErrorCode
from src.projects.dto import DeleteProjectCommand
from src.projects.use_cases import DeleteProjectUseCase
from src.shared.errors import ConflictError, DatabaseError, NotFoundError


def create_chat(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> tuple[ConversationScope, dict[str, str], str]:
    monkeypatch.setattr(settings.assistant, "enabled", True)
    owner = _register_and_login(
        client, username="assistant_lifecycle", email="assistant_lifecycle@example.com"
    )
    project = _create_project(client, token=owner["token"], name="Lifecycle")
    headers = {"Authorization": f"Bearer {owner['token']}"}
    base = f"/api/projects/{project['id']}/assistant/conversations"
    chat = client.post(base, headers=headers, json={"title": "Lifecycle"})
    assert chat.status_code == 201
    scope = ConversationScope(
        project_id=project["id"],
        user_id=owner["user"]["id"],
        conversation_id=UUID(chat.json()["id"]),
    )
    return scope, headers, f"{base}/{scope.conversation_id}"


def pending_plan(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> tuple[ConversationScope, dict[str, str], str, dict[str, Any]]:
    asyncio.run(setup_checkpointer())
    scope, headers, path = create_chat(client, monkeypatch)
    replies = iter(
        [
            AIMessage(
                content="",
                tool_calls=[{"id": "column", "name": "CreateColumn", "args": {"name": "Work"}}],
            ),
            AIMessage(content="Finished"),
        ]
    )

    async def call_model(*args: Any) -> ModelAnswer:
        return ModelAnswer(next(replies), "test", "test", False, 0)

    monkeypatch.setattr(graph_module, "call_model", call_model)
    response = client.post(f"{path}/runs", headers=headers, json={"content": "Create column"})
    assert response.status_code == 200
    run = client.get(path, headers=headers).json()["latestRun"]
    assert run["status"] == "pending"
    return scope, headers, path, run


def test_concurrent_starts_create_one_run(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope, _, _ = create_chat(client, monkeypatch)

    async def exercise() -> None:
        command = StartRunCommand(**vars(scope), content="Question")
        outcomes = await asyncio.gather(
            *[StartRunUseCase(UnitOfWork).execute(command) for _ in range(4)],
            return_exceptions=True,
        )
        assert sum(not isinstance(outcome, BaseException) for outcome in outcomes) == 1
        conflicts = [outcome for outcome in outcomes if isinstance(outcome, ConflictError)]
        assert len(conflicts) == 3
        assert all(error.code == ErrorCode.ASSISTANT_RUN_ACTIVE for error in conflicts)
        async with db_helper.async_session_maker() as session:
            runs = await AssistantRepository(session).list_runs(scope.conversation_id)
            assert len(runs) == 1 and runs[0].status == "running"
        await AssistantRunLifecycle(UnitOfWork).interrupt(runs[0].id)

    asyncio.run(exercise())


@pytest.mark.parametrize("target", ["chat", "project"])
def test_delete_rollback_preserves_pending_checkpoint(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    scope, headers, path, run = pending_plan(client, monkeypatch)

    class FailingUnitOfWork(UnitOfWork):
        async def commit(self) -> None:
            await self.rollback()
            raise RuntimeError("Simulated commit failure")

    async def exercise() -> None:
        cleanup = CheckpointCleanup(UnitOfWork)
        expected_error = RuntimeError if target == "chat" else DatabaseError
        with pytest.raises(expected_error):
            if target == "chat":
                await DeleteConversationUseCase(FailingUnitOfWork, cleanup).execute(scope)
            else:
                await DeleteProjectUseCase(
                    FailingUnitOfWork, deletion_hook=AssistantProjectDeletionHook(cleanup)
                ).execute(
                    DeleteProjectCommand(project_id=scope.project_id, actor_user_id=scope.user_id)
                )
        async with db_helper.async_session_maker() as session:
            assert await session.get(AssistantConversation, scope.conversation_id) is not None
            assert (
                await session.scalar(select(func.count()).select_from(AssistantCheckpointCleanup))
                == 0
            )
        async with open_checkpointer() as saver:
            assert await saver.aget_tuple({"configurable": {"thread_id": run["id"]}}) is not None

    asyncio.run(exercise())
    restored = client.get(path, headers=headers).json()["latestRun"]
    assert restored["status"] == "pending"
    decision = client.post(
        f"{path}/runs/{run['id']}/decision",
        headers=headers,
        json={
            "action_id": run["proposedAction"]["action_id"],
            "approve": True,
        },
    )
    assert decision.status_code == 200
    assert client.get(path, headers=headers).json()["latestRun"]["status"] == "completed"


def test_checkpoint_cleanup_retries_after_committed_delete(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope, _, _, run = pending_plan(client, monkeypatch)

    class UnavailableSaver:
        async def adelete_thread(self, thread_id: str) -> None:
            raise RuntimeError("Temporary checkpoint connection failure")

    @asynccontextmanager
    async def unavailable_checkpointer():
        yield UnavailableSaver()

    async def exercise() -> None:
        cleanup = CheckpointCleanup(UnitOfWork, unavailable_checkpointer)  # type: ignore[arg-type]
        await DeleteConversationUseCase(UnitOfWork, cleanup).execute(scope)
        async with db_helper.async_session_maker() as session:
            assert await session.get(AssistantConversation, scope.conversation_id) is None
            assert await session.get(AssistantCheckpointCleanup, UUID(run["id"])) is not None
        await CheckpointCleanup(UnitOfWork).drain()
        async with db_helper.async_session_maker() as session:
            assert await session.get(AssistantCheckpointCleanup, UUID(run["id"])) is None
        async with open_checkpointer() as saver:
            assert await saver.aget_tuple({"configurable": {"thread_id": run["id"]}}) is None

    asyncio.run(exercise())


def test_decision_and_delete_are_serialized(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope, _, _, run = pending_plan(client, monkeypatch)

    async def exercise() -> None:
        decision = DecideActionCommand(
            **vars(scope),
            run_id=UUID(run["id"]),
            action_id=run["proposedAction"]["action_id"],
            approve=True,
        )
        outcomes = await asyncio.gather(
            DecideActionUseCase(UnitOfWork).execute(decision),
            DeleteConversationUseCase(UnitOfWork, CheckpointCleanup(UnitOfWork)).execute(scope),
            return_exceptions=True,
        )
        if isinstance(outcomes[0], NotFoundError):
            assert outcomes[1] is None
        else:
            assert not isinstance(outcomes[0], BaseException)
            assert isinstance(outcomes[1], ConflictError)
            assert outcomes[1].code == ErrorCode.ASSISTANT_RUN_ACTIVE
            await AssistantRunLifecycle(UnitOfWork).interrupt(UUID(run["id"]))
            await DeleteConversationUseCase(UnitOfWork, CheckpointCleanup(UnitOfWork)).execute(
                scope
            )

    asyncio.run(exercise())


def test_active_run_blocks_project_deletion(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope, headers, path = create_chat(client, monkeypatch)
    execution = asyncio.run(
        StartRunUseCase(UnitOfWork).execute(StartRunCommand(**vars(scope), content="Question"))
    )
    response = client.delete(f"/api/projects/{scope.project_id}", headers=headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == ErrorCode.ASSISTANT_RUN_ACTIVE
    assert client.get(path, headers=headers).status_code == 200
    asyncio.run(AssistantRunLifecycle(UnitOfWork).interrupt(execution.run_id))
    assert client.delete(f"/api/projects/{scope.project_id}", headers=headers).status_code == 204
