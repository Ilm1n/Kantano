# ruff: noqa: RUF001
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_assistant_project_tools import NoopCache, RecordingPublisher
from test_create_task_slice import _create_column, _create_project, _register_and_login

from src.assistant.dependencies import make_assistant_tools
from src.assistant.dto import ProjectScope
from src.assistant.queries import AssistantProjectQueries
from src.boards.models import Task
from src.db.database import db_helper


def test_task_search_returns_readable_summaries_and_full_details(client: TestClient) -> None:
    owner = _register_and_login(
        client, username="assistant_summary", email="assistant_summary@example.com"
    )
    project = _create_project(client, token=owner["token"], name="Summary project")
    other = _create_project(client, token=owner["token"], name="Other project")
    asyncio.run(_exercise_summaries(project["id"], other["id"], owner["user"]))


async def _exercise_summaries(project_id: int, other_id: int, user: dict[str, Any]) -> None:
    tools = make_assistant_tools(
        ProjectScope(project_id=project_id, user_id=user["id"]),
        RecordingPublisher(),  # type: ignore[arg-type]
        NoopCache(),  # type: ignore[arg-type]
    )
    column = await tools.execute_write("CreateColumn", {"name": "Работа"})
    tag = await tools.execute_write("CreateTag", {"name": "Баг", "color": "#0000FF"})
    description = "Описание " + "а" * 310 + " searchable tail"
    task = await tools.execute_write(
        "CreateTask",
        {
            "title": "Задача с исполнителем",
            "column_id": column["column_id"],
            "description": description,
            "assignee_id": user["id"],
            "priority": "HIGH",
            "deadline_at": "2026-10-02T00:00:00+00:00",
            "tag_ids": [tag["tag_id"]],
        },
    )
    await tools.execute_write(
        "CreateTask", {"title": "Пустая задача", "column_id": column["column_id"]}
    )
    page = await tools.read("SearchTasks", {})
    assert len(page["tasks"]) == 2
    assert page["next_offset"] is None
    summary = next(t for t in page["tasks"] if t["id"] == task["task_id"])
    assert summary["column_name"] == "Работа"
    assert summary["assignee_id"] == user["id"]
    assert summary["assignee_name"] == (user.get("fullName") or user["username"])
    assert summary["priority"] == "HIGH"
    assert datetime.fromisoformat(summary["deadline_at"]) == datetime(2026, 10, 2, tzinfo=UTC)
    assert summary["tags"] == [{"id": tag["tag_id"], "name": "Баг", "color": "#0000FF"}]
    assert summary["description_preview"] == description[:300]
    assert summary["description_truncated"] is True
    assert datetime.fromisoformat(summary["updated_at"]).tzinfo is not None
    empty = next(t for t in page["tasks"] if t["id"] != task["task_id"])
    assert empty["description_preview"] == ""
    assert empty["description_truncated"] is False
    assert empty["assignee_name"] is None
    assert empty["deadline_at"] is None
    assert empty["tags"] == []
    # Search covers the full stored description, even beyond the returned preview.
    for filters in (
        {"search": "searchable tail"},
        {"assignee_id": user["id"]},
        {"tag_id": tag["tag_id"]},
        {"search": "исполнителем", "assignee_id": user["id"], "tag_id": tag["tag_id"]},
    ):
        found = await tools.read("SearchTasks", filters)
        assert [t["id"] for t in found["tasks"]] == [task["task_id"]]
    full = await tools.read("GetTask", {"task_id": task["task_id"]})
    assert full["description"] == description
    assert full["assignee_name"] == summary["assignee_name"]
    assert full["column_name"] == summary["column_name"]
    other_queries = AssistantProjectQueries(
        db_helper.async_session_maker, ProjectScope(project_id=other_id, user_id=user["id"])
    )
    assert (await other_queries.read("SearchTasks", {}))["tasks"] == []
    with pytest.raises(ValueError, match="Task not found in this project"):
        await other_queries.read("GetTask", {"task_id": task["task_id"]})


def test_task_search_pages_have_stable_order_and_preserve_regular_api(client: TestClient) -> None:
    owner = _register_and_login(
        client, username="assistant_pages", email="assistant_pages@example.com"
    )
    project = _create_project(client, token=owner["token"], name="Paged tasks")
    column = _create_column(client, token=owner["token"], project_id=project["id"])
    asyncio.run(_exercise_pages(project["id"], column["id"], owner["user"]["id"]))
    response = client.get(
        f"/api/projects/{project['id']}/tasks",
        headers={"Authorization": f"Bearer {owner['token']}"},
    )
    assert response.status_code == 200
    assert len(response.json()) == 31


async def _exercise_pages(project_id: int, column_id: int, user_id: int) -> None:
    async with db_helper.async_session_maker() as session:
        tasks = [
            Task(
                title=f"Paged task {i}",
                project_id=project_id,
                column_id=column_id,
                position=float(i),
                updated_at=datetime(2026, 9, 30, tzinfo=UTC),
            )
            for i in range(31)
        ]
        session.add_all(tasks)
        await session.commit()
        expected_ids = sorted((t.id for t in tasks), reverse=True)
    queries = AssistantProjectQueries(
        db_helper.async_session_maker, ProjectScope(project_id=project_id, user_id=user_id)
    )
    first = await queries.read("SearchTasks", {})
    assert [t["id"] for t in first["tasks"]] == expected_ids[:30]
    assert first["truncated"] is True
    assert first["next_offset"] == 30
    last = await queries.read("SearchTasks", {"offset": first["next_offset"]})
    assert [t["id"] for t in last["tasks"]] == expected_ids[30:]
    assert last["truncated"] is False
    assert last["next_offset"] is None
    filtered = await queries.read("SearchTasks", {"search": "Paged task", "limit": 2})
    assert filtered["next_offset"] == 2
    following = await queries.read(
        "SearchTasks", {"search": "Paged task", "limit": 2, "offset": filtered["next_offset"]}
    )
    assert [t["id"] for t in following["tasks"]] == expected_ids[2:4]
    assert following["next_offset"] == 4
    assert (await queries.read("SearchTasks", {"offset": 31}))["tasks"] == []
    outsider = AssistantProjectQueries(
        db_helper.async_session_maker, ProjectScope(project_id=project_id, user_id=-1)
    )
    with pytest.raises(ValueError, match="Project access"):
        await outsider.read("SearchTasks", {})
