from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from test_create_task_slice import _create_project, _register_and_login

from src.assistant.tools import AssistantTools


class RecordingPublisher:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def publish_event(self, **kwargs) -> None:
        self.events.append(str(kwargs["event_type"]))


class NoopCache:
    async def invalidate_board(self, project_id: int) -> None:
        pass

    async def invalidate_tags(self, project_id: int) -> None:
        pass


def test_assistant_manages_columns_and_tags_with_existing_use_cases(
    client: TestClient,
) -> None:
    owner = _register_and_login(
        client, username="assistant_tools", email="assistant_tools@example.com"
    )
    project = _create_project(client, token=owner["token"], name="Assistant tools")
    other_project = _create_project(client, token=owner["token"], name="Other project")
    asyncio.run(_exercise_tools(project["id"], other_project["id"], owner["user"]["id"]))


async def _exercise_tools(project_id: int, other_project_id: int, user_id: int) -> None:
    publisher = RecordingPublisher()
    tools = AssistantTools(
        project_id=project_id,
        user_id=user_id,
        event_publisher=publisher,  # type: ignore[arg-type]
        cache=NoopCache(),  # type: ignore[arg-type]
    )

    first = await tools.execute_write("CreateColumn", {"name": "Первое"})
    second = await tools.execute_write("CreateColumn", {"name": "Второе"})
    await tools.execute_write(
        "MoveColumn", {"column_id": second["column_id"], "before_column_id": first["column_id"]}
    )
    await tools.execute_write(
        "RenameColumn", {"column_id": second["column_id"], "new_name": "Начало"}
    )
    overview = await tools.read("ProjectOverview", {})
    assert [column["name"] for column in overview["columns"]] == ["Начало", "Первое"]

    keep = await tools.execute_write("CreateTag", {"name": "Оставить"})
    target = await tools.execute_write("CreateTag", {"name": "Временный", "color": "#123456"})
    await tools.execute_write(
        "UpdateTag", {"tag_id": target["tag_id"], "name": "Важный", "color": "#ABCDEF"}
    )
    task = await tools.execute_write(
        "CreateTask",
        {
            "title": "Проверка тегов",
            "column_id": first["column_id"],
            "tag_ids": [keep["tag_id"]],
        },
    )
    await tools.execute_write(
        "AddTagToTask", {"task_id": task["task_id"], "tag_id": target["tag_id"]}
    )
    with_added = await tools.read("GetTask", {"task_id": task["task_id"]})
    assert {tag["id"] for tag in with_added["tags"]} == {keep["tag_id"], target["tag_id"]}

    await tools.execute_write(
        "RemoveTagFromTask", {"task_id": task["task_id"], "tag_id": target["tag_id"]}
    )
    with_removed = await tools.read("GetTask", {"task_id": task["task_id"]})
    assert [tag["id"] for tag in with_removed["tags"]] == [keep["tag_id"]]
    overview = await tools.read("ProjectOverview", {})
    assert {tag["name"]: tag["color"] for tag in overview["tags"]}["Важный"] == "#ABCDEF"
    other_tools = AssistantTools(
        project_id=other_project_id,
        user_id=user_id,
        event_publisher=publisher,  # type: ignore[arg-type]
        cache=NoopCache(),  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match="this project"):
        await other_tools.execute_write(
            "UpdateTag", {"tag_id": target["tag_id"], "name": "Wrong project"}
        )
    assert publisher.events
