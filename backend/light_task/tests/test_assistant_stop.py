# ruff: noqa: RUF001
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from test_assistant_lifecycle import create_chat, pending_plan
from test_assistant_project_tools import NoopCache, RecordingPublisher

from src.assistant import graph as graph_module
from src.assistant.dependencies import make_assistant_tools
from src.assistant.dto import DecideActionCommand, StartRunCommand, StopRunCommand
from src.assistant.provider import ModelAnswer
from src.assistant.repository import AssistantRepository
from src.assistant.runtime import AssistantRuntime, StreamEvent
from src.assistant.tools import AssistantTools
from src.assistant.use_cases import (
    AssistantRunLifecycle,
    DecideActionUseCase,
    StartRunUseCase,
    StopRunUseCase,
)
from src.db.database import db_helper
from src.db.unit_of_work import UnitOfWork


def test_stop_cancels_llm_without_an_assistant_message(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope, headers, path = create_chat(client, monkeypatch)

    async def exercise() -> None:
        entered = asyncio.Event()
        cancelled = asyncio.Event()

        async def call_model(*args: Any, **kwargs: Any) -> ModelAnswer:
            entered.set()
            try:
                await asyncio.sleep(30)
            finally:
                cancelled.set()
            raise AssertionError("Model should have been cancelled")

        monkeypatch.setattr(graph_module, "call_model", call_model)
        saver = InMemorySaver()

        @asynccontextmanager
        async def checkpointer() -> AsyncIterator[InMemorySaver]:
            yield saver

        runtime = AssistantRuntime(
            lambda s: make_assistant_tools(s, RecordingPublisher(), NoopCache()),  # type: ignore[arg-type]
            AssistantRunLifecycle(UnitOfWork),
            checkpointer,  # type: ignore[arg-type]
        )
        execution = await StartRunUseCase(UnitOfWork).execute(
            StartRunCommand(**vars(scope), content="Question")
        )
        events: list[StreamEvent] = []

        async def consume() -> None:
            events.extend([event async for event in runtime.stream(execution)])

        streaming = asyncio.create_task(consume())
        await asyncio.wait_for(entered.wait(), 5)
        command = StopRunCommand(**vars(scope), run_id=execution.run_id)
        await StopRunUseCase(UnitOfWork).execute(command)
        await StopRunUseCase(UnitOfWork).execute(command)
        await asyncio.wait_for(streaming, 5)
        assert cancelled.is_set()
        assert events[-1] == ("done", {"status": "cancelled", "message": ""})
        assert all(name != "error" for name, _ in events)
        async with db_helper.async_session_maker() as session:
            repository = AssistantRepository(session)
            messages = await repository.list_messages(scope.conversation_id)
            assert [message.role for message in messages] == ["user"]
            run = await repository.get_run(execution.run_id)
            assert run is not None and run.status == "cancelled"
        next_execution = await StartRunUseCase(UnitOfWork).execute(
            StartRunCommand(**vars(scope), content="Next")
        )
        await AssistantRunLifecycle(UnitOfWork).interrupt(next_execution.run_id)

    asyncio.run(exercise())
    assert client.post(f"{path}/runs/{uuid4()}/stop", headers=headers).status_code == 404


@pytest.mark.parametrize("unknown", [False, True])
def test_stop_finishes_started_write_and_does_not_start_next_step(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, unknown: bool
) -> None:
    scope, _, _ = create_chat(client, monkeypatch)

    async def exercise() -> None:
        entered, release = asyncio.Event(), asyncio.Event()
        calls: list[str] = []
        original_write = AssistantTools.execute_write

        async def blocked_write(
            self: AssistantTools, name: str, args: dict[str, Any]
        ) -> dict[str, Any]:
            calls.append(name)
            entered.set()
            await release.wait()
            result = await original_write(self, name, args)
            if unknown:
                raise RuntimeError("Unknown post-commit outcome")
            return result

        monkeypatch.setattr(AssistantTools, "execute_write", blocked_write)
        llm_calls = 0

        async def call_model(*args: Any, **kwargs: Any) -> ModelAnswer:
            nonlocal llm_calls
            llm_calls += 1
            assert llm_calls == 1, "Stopping must not call the model for a summary"
            return ModelAnswer(
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "plan",
                            "name": "ExecutePlan",
                            "args": {
                                "steps": [
                                    {
                                        "id": "first",
                                        "tool": "CreateColumn",
                                        "args": {"name": "First"},
                                    },
                                    {
                                        "id": "second",
                                        "tool": "CreateTask",
                                        "args": {
                                            "column_id": "$first.column_id",
                                            "title": "Second",
                                        },
                                    },
                                ]
                            },
                        }
                    ],
                ),
                "test",
                "test",
                False,
                0,
            )

        monkeypatch.setattr(graph_module, "call_model", call_model)
        saver = InMemorySaver()

        @asynccontextmanager
        async def checkpointer() -> AsyncIterator[InMemorySaver]:
            yield saver

        tools = make_assistant_tools(scope, RecordingPublisher(), NoopCache())  # type: ignore[arg-type]
        lifecycle = AssistantRunLifecycle(UnitOfWork)
        runtime = AssistantRuntime(lambda s: tools, lifecycle, checkpointer)  # type: ignore[arg-type]
        execution = await StartRunUseCase(UnitOfWork).execute(
            StartRunCommand(**vars(scope), content="Plan")
        )
        events = [event async for event in runtime.stream(execution)]
        assert events[-1][0] == "approval_required"
        proposal = events[-1][1]["action"]
        execution = await DecideActionUseCase(UnitOfWork).execute(
            DecideActionCommand(
                **vars(scope),
                run_id=execution.run_id,
                action_id=proposal["action_id"],
                approve=True,
            )
        )

        async def consume() -> list[StreamEvent]:
            return [event async for event in runtime.stream(execution)]

        streaming = asyncio.create_task(consume())
        await asyncio.wait_for(entered.wait(), 5)
        await StopRunUseCase(UnitOfWork).execute(
            StopRunCommand(**vars(scope), run_id=execution.run_id)
        )
        assert not streaming.done()
        release.set()
        events = await asyncio.wait_for(streaming, 5)
        assert calls == ["CreateColumn"]
        overview = await tools.read("ProjectOverview", {})
        assert [column["name"] for column in overview["columns"]] == ["First"]
        async with db_helper.async_session_maker() as session:
            repository = AssistantRepository(session)
            run = await repository.get_run(execution.run_id)
            assert run is not None
            assert run.status == ("unknown" if unknown else "cancelled")
            messages = await repository.list_messages(scope.conversation_id)
            if not unknown:
                assert [item["status"] for item in run.result["actions"]] == [
                    "completed",
                    "cancelled",
                ]
                assert "Создана колонка «First»" in messages[-1].content
                assert "Не создана задача «Second»" in messages[-1].content
                assert events[-1][0] == "done"
            else:
                assert events[-1][0] == "error"
        assert llm_calls == 1

    asyncio.run(exercise())


def test_stop_that_reaches_pending_is_idempotent_and_prevents_confirmation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scope, headers, path, run = pending_plan(client, monkeypatch)
    url = f"{path}/runs/{run['id']}/stop"
    assert client.post(url, headers=headers).status_code == 204
    assert client.post(url, headers=headers).status_code == 204
    detail = client.get(path, headers=headers).json()
    assert detail["latestRun"]["status"] == "cancelled"
    assert [message["role"] for message in detail["messages"]] == ["user"]
    decision = client.post(
        f"{path}/runs/{run['id']}/decision",
        headers=headers,
        json={
            "approve": True,
            "action_id": run["proposedAction"]["action_id"],
        },
    )
    assert decision.status_code == 409
    assert client.post(f"{path}/runs/{UUID(run['id'])}/stop", headers=headers).status_code == 204
