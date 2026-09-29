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
from src.assistant.router import interrupt_active_run
from src.config import settings
from src.db.database import db_helper


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
def test_sequential_actions_preserve_results_and_reject_stale_decisions(
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
    previous_action_id: str | None = None
    for i in range(4):
        detail = client.get(chat_path, headers=headers).json()
        assert detail["latestRun"]["status"] == "pending"
        action_id = detail["latestRun"]["proposedAction"]["action_id"]
        assert action_id != previous_action_id
        board = client.get(f"/api/projects/{project['id']}/columns", headers=headers).json()
        assert len(board[0]["tasks"]) == i
        if previous_action_id:
            stale = client.post(
                decision_path,
                headers=headers,
                json={"approve": True, "action_id": previous_action_id},
            )
            assert stale.status_code == 409
        run_events = events(
            client.post(
                decision_path, headers=headers, json={"approve": True, "action_id": action_id}
            )
        )
        assert not any(name == "error" for name, _ in run_events) or (fail_summary and i == 3)
        previous_action_id = action_id
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
    assert len([message for message in detail["messages"] if message.get("references")]) == 4
    repeated = client.post(
        decision_path, headers=headers, json={"approve": True, "action_id": previous_action_id}
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
            await interrupt_active_run(run.id)
        async with db_helper.async_session_maker() as session:
            states = [(await session.get(AssistantRun, run.id)).status for run in runs]
            assert states == ["interrupted", "unknown", "pending", "completed", "failed"]

    asyncio.run(exercise())
