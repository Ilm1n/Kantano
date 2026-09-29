from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from test_create_task_slice import _create_column, _create_project, _register_and_login

from src.assistant import graph as graph_module
from src.assistant.checkpoints import setup_checkpointer
from src.assistant.models import AssistantConversation, AssistantRun
from src.assistant.provider import ModelAnswer
from src.assistant.tools import AssistantTools
from src.assistant.use_cases import AssistantRunLifecycle
from src.config import settings
from src.db.database import db_helper
from src.db.unit_of_work import UnitOfWork
from src.errors import ErrorCode
from src.shared.errors import BadRequestError


def events(response: Any) -> list[tuple[str, dict[str, Any]]]:
    assert response.status_code == 200, response.text
    result = []
    for block in response.text.strip().split("\n\n"):
        lines = block.splitlines()
        result.append(
            (lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: ")))
        )
    return result


@pytest.mark.parametrize("fail_summary", [False, True])
def test_plan_preserves_results_and_rejects_repeated_decisions(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, fail_summary: bool
) -> None:
    monkeypatch.setattr(settings.assistant, "enabled", True)
    asyncio.run(setup_checkpointer())
    owner = _register_and_login(
        client, username="assistant_runs", email="assistant_runs@example.com"
    )
    headers = {"Authorization": f"Bearer {owner['token']}"}
    project = _create_project(client, token=owner["token"], name="Assistant runs")
    column = _create_column(client, token=owner["token"], project_id=project["id"])
    tag_response = client.post(
        f"/api/projects/{project['id']}/tags",
        headers=headers,
        json={"name": "Tag", "color": "#123456"},
    )
    assert tag_response.status_code == 201
    calls = 0

    async def call_model(*args: Any) -> ModelAnswer:
        nonlocal calls
        calls += 1
        if calls == 1:
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": f"task-{i}",
                        "name": "CreateTask",
                        "args": {
                            "title": f"Task {i}",
                            "column_id": column["id"],
                            "description": "Description",
                            "priority": "Высокий",
                            "assignee_id": owner["user"]["id"],
                            "deadline_at": "2026-10-01",
                            "tag_ids": [tag_response.json()["id"]],
                        },
                    }
                    for i in range(4)
                ],
            )
        elif fail_summary:
            raise RuntimeError("Model unavailable after successful writes")
        else:
            message = AIMessage(content="Finished")
        return ModelAnswer(message, "test", "test", False, 0)

    monkeypatch.setattr(graph_module, "call_model", call_model)
    base = f"/api/projects/{project['id']}/assistant/conversations"
    chat = client.post(base, headers=headers, json={"title": "Test"})
    assert chat.status_code == 201
    chat_path = f"{base}/{chat.json()['id']}"
    run_events = events(
        client.post(f"{chat_path}/runs", headers=headers, json={"content": "Create four tasks"})
    )
    run_id = next(data["run_id"] for name, data in run_events if name == "run")
    decision_path = f"{chat_path}/runs/{run_id}/decision"
    detail = client.get(chat_path, headers=headers).json()
    assert detail["latestRun"]["status"] == "pending"
    proposal = detail["latestRun"]["proposedAction"]
    action_id = proposal["action_id"]
    assert proposal["name"] == "ExecutePlan"
    assert len(proposal["display"]["steps"]) == 4
    display = proposal["display"]["steps"][0]["display"]
    assert display["assignee_id"] == owner["user"]["username"]
    assert display["column_id"] == column["name"]
    assert display["tag_ids"] == ["Tag"]
    board = client.get(f"/api/projects/{project['id']}/columns", headers=headers).json()
    assert len(board[0]["tasks"]) == 0
    run_events = events(
        client.post(decision_path, headers=headers, json={"approve": True, "action_id": action_id})
    )
    assert any(name == "error" for name, _ in run_events) == fail_summary
    detail = client.get(chat_path, headers=headers).json()
    run = detail["latestRun"]
    assert run["status"] == ("failed" if fail_summary else "completed")
    assert len(run["result"]["actions"]) == 4
    assert all(outcome["status"] == "completed" for outcome in run["result"]["actions"])
    board = client.get(f"/api/projects/{project['id']}/columns", headers=headers).json()
    assert len(board[0]["tasks"]) == 4
    assert all(
        task["priority"] == "HIGH" and task["assigneeId"] == owner["user"]["id"]
        for task in board[0]["tasks"]
    )
    result_messages = [message for message in detail["messages"] if message.get("references")]
    assert len(result_messages) == 1
    assert [ref["title"] for ref in result_messages[0]["references"]] == [
        f"Task {i}" for i in range(4)
    ]
    repeated = client.post(
        decision_path, headers=headers, json={"approve": True, "action_id": action_id}
    )
    assert repeated.status_code == 409
    assert client.delete(chat_path, headers=headers).status_code == 204


def test_disconnect_cleanup_only_finishes_active_runs(client: TestClient) -> None:
    owner = _register_and_login(
        client, username="assistant_cleanup", email="assistant_cleanup@example.com"
    )
    project = _create_project(client, token=owner["token"], name="Cleanup")

    async def exercise() -> None:
        async with db_helper.async_session_maker() as session:
            conversation = AssistantConversation(
                project_id=project["id"], user_id=owner["user"]["id"], mode="local"
            )
            session.add(conversation)
            await session.flush()
            runs = [
                AssistantRun(id=uuid4(), conversation_id=conversation.id, status=status)
                for status in ("running", "executing", "pending", "completed", "failed")
            ]
            session.add_all(runs)
            await session.commit()
        for run in runs:
            await AssistantRunLifecycle(UnitOfWork).interrupt(run.id)
        async with db_helper.async_session_maker() as session:
            states = [(await session.get(AssistantRun, run.id)).status for run in runs]
            assert states == ["interrupted", "unknown", "pending", "completed", "failed"]

    asyncio.run(exercise())


@pytest.mark.parametrize("failure", [None, "known", "unknown"])
def test_mixed_dependent_plan_and_partial_results(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    monkeypatch.setattr(settings.assistant, "enabled", True)
    asyncio.run(setup_checkpointer())
    owner = _register_and_login(
        client, username="assistant_plan", email="assistant_plan@example.com"
    )
    headers = {"Authorization": f"Bearer {owner['token']}"}
    project = _create_project(client, token=owner["token"], name="Empty project")
    steps = [
        {"id": "work", "tool": "CreateColumn", "args": {"name": "Work"}},
        {"id": "tag", "tool": "CreateTag", "args": {"name": "Feature"}},
        {
            "id": "first",
            "tool": "CreateTask",
            "args": {"title": "One", "column_id": "$work.column_id", "tag_ids": ["$tag.tag_id"]},
        },
        {
            "id": "second",
            "tool": "CreateTask",
            "args": {"title": "Two", "column_id": "$work.column_id"},
        },
        {
            "id": "rename",
            "tool": "RenameColumn",
            "args": {"column_id": "$work.column_id", "new_name": "Development"},
        },
        {
            "id": "assign",
            "tool": "UpdateTask",
            "args": {"task_id": "$first.task_id", "assignee_id": owner["user"]["id"]},
        },
        {
            "id": "untag",
            "tool": "RemoveTagFromTask",
            "args": {"task_id": "$first.task_id", "tag_id": "$tag.tag_id"},
        },
    ]
    replies = iter(
        [
            AIMessage(
                content="",
                tool_calls=[{"id": "plan", "name": "ExecutePlan", "args": {"steps": steps}}],
            ),
            AIMessage(content="Finished"),
        ]
    )

    async def call_model(*args: Any) -> ModelAnswer:
        return ModelAnswer(next(replies), "test", "test", False, 0)

    original_write = AssistantTools.execute_write

    async def execute_write(
        self: AssistantTools, name: str, args: dict[str, Any]
    ) -> dict[str, Any]:
        if failure and name == "CreateTask" and args["title"] == "Two":
            if failure == "known":
                raise BadRequestError(ErrorCode.COLUMN_TASK_LIMIT_REACHED)
            raise RuntimeError("Unknown write outcome")
        return await original_write(self, name, args)

    monkeypatch.setattr(graph_module, "call_model", call_model)
    monkeypatch.setattr(AssistantTools, "execute_write", execute_write)
    base = f"/api/projects/{project['id']}/assistant/conversations"
    chat = client.post(base, headers=headers, json={"title": "Plan"}).json()
    chat_path = f"{base}/{chat['id']}"
    events(client.post(f"{chat_path}/runs", headers=headers, json={"content": "Build structure"}))
    pending = client.get(chat_path, headers=headers).json()["latestRun"]
    display = pending["proposedAction"]["display"]["steps"]
    assert display[2]["display"]["column_id"] == "Work"
    assert display[2]["display"]["tag_ids"] == ["Feature"]
    assert display[5]["display"]["task_id"] == "One"
    assert client.get(f"/api/projects/{project['id']}/columns", headers=headers).json() == []
    decision_path = f"{chat_path}/runs/{pending['id']}/decision"
    decision = {"approve": True, "action_id": pending["proposedAction"]["action_id"]}
    events(client.post(decision_path, headers=headers, json=decision))
    detail = client.get(chat_path, headers=headers).json()
    run = detail["latestRun"]
    assert run["status"] == {None: "completed", "known": "failed", "unknown": "unknown"}[failure]
    board = client.get(f"/api/projects/{project['id']}/columns", headers=headers).json()
    assert len(board) == 1
    assert len(board[0]["tasks"]) == (1 if failure else 2)
    assert board[0]["name"] == ("Work" if failure else "Development")
    assert len(run["result"]["actions"]) == (3 if failure == "unknown" else 7)
    if not failure:
        first = next(task for task in board[0]["tasks"] if task["title"] == "One")
        assert first["assigneeId"] == owner["user"]["id"]
        assert first["tags"] == []
    assert client.post(decision_path, headers=headers, json=decision).status_code == 409
