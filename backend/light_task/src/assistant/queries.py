# ruff: noqa: RUF001
from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from src.assistant.dto import ProjectScope
from src.assistant.plans import ID_FIELDS, REFERENCE
from src.assistant.repository import AssistantRepository
from src.assistant.tool_schemas import GetTask, SearchTasks
from src.boards.repository import BoardRepository

DESCRIPTION_PREVIEW_LENGTH = 300


class AssistantProjectQueries:
    def __init__(self, session_factory: Callable[[], AsyncSession], scope: ProjectScope) -> None:
        self._session_factory = session_factory
        self.project_id = scope.project_id
        self.user_id = scope.user_id

    async def read(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        async with self._session_factory() as session:
            repository = BoardRepository(session)
            context = AssistantRepository(session)
            if not await repository.project_member_exists(
                project_id=self.project_id, user_id=self.user_id
            ):
                raise ValueError("Project access is no longer available")
            if name == "ProjectOverview":
                project = await context.get_project(self.project_id)
                if project is None:
                    raise ValueError("Project no longer exists")
                columns = await context.project_columns(self.project_id)
                counts = await context.task_counts(self.project_id)
                members = await context.project_users(self.project_id)
                tags = await context.project_tags(self.project_id)
                return {
                    "project": {
                        "id": project.id,
                        "name": project.name,
                        "description": project.description,
                    },
                    "columns": [
                        {
                            "id": c.id,
                            "name": c.name,
                            "task_count": counts.get(c.id, 0),
                        }
                        for c in columns
                    ],
                    "members": [
                        {"id": m.id, "username": m.username, "name": m.full_name} for m in members
                    ],
                    "tags": [{"id": t.id, "name": t.name, "color": t.color} for t in tags],
                }
            if name == "SearchTasks":
                query = SearchTasks.model_validate(args)
                tasks = await repository.list_project_tasks(
                    project_id=self.project_id,
                    search=query.search,
                    assignee_id=query.assignee_id,
                    tag_ids=[query.tag_id] if query.tag_id else None,
                    limit=query.limit + 1,
                    offset=query.offset,
                )
                columns = {c.id: c.name for c in await context.project_columns(self.project_id)}
                has_more = len(tasks) > query.limit
                return {
                    "tasks": [
                        {
                            "id": t.id,
                            "title": t.title,
                            "column_id": t.column_id,
                            "column_name": columns.get(t.column_id),
                            "priority": t.priority.value if t.priority else None,
                            "assignee_id": t.assignee_id,
                            "assignee_name": (t.assignee.full_name or t.assignee.username)
                            if t.assignee
                            else None,
                            "deadline_at": t.deadline_at.isoformat() if t.deadline_at else None,
                            "tags": [
                                {"id": tag.id, "name": tag.name, "color": tag.color}
                                for tag in t.tags
                            ],
                            "description_preview": (t.description or "")[
                                :DESCRIPTION_PREVIEW_LENGTH
                            ],
                            "description_truncated": len(t.description or "")
                            > DESCRIPTION_PREVIEW_LENGTH,
                            "updated_at": t.updated_at.isoformat(),
                        }
                        for t in tasks[: query.limit]
                    ],
                    "truncated": has_more,
                    "next_offset": query.offset + query.limit if has_more else None,
                }
            if name == "GetTask":
                query = GetTask.model_validate(args)
                task = await repository.get_task_with_tags(query.task_id)
                if task is None or task.project_id != self.project_id:
                    raise ValueError("Task not found in this project")
                members = await context.project_users(self.project_id) if task.assignee_id else []
                assignee = next((m for m in members if m.id == task.assignee_id), None)
                return {
                    "id": task.id,
                    "title": task.title,
                    "description": task.description,
                    "column_id": task.column_id,
                    "column_name": await context.entity_label(
                        "column", self.project_id, task.column_id
                    ),
                    "priority": task.priority.value if task.priority else None,
                    "assignee_id": task.assignee_id,
                    "assignee_name": (assignee.full_name or assignee.username)
                    if assignee
                    else None,
                    "deadline_at": task.deadline_at.isoformat() if task.deadline_at else None,
                    "tags": [
                        {"id": tag.id, "name": tag.name, "color": tag.color} for tag in task.tags
                    ],
                    "updated_at": task.updated_at.isoformat(),
                }
            raise ValueError("Unknown read tool")

    async def describe_action(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "ExecutePlan":
            steps = []
            planned: dict[str, str] = {}
            for step in args["steps"]:
                fields = dict(step["args"])
                deferred: dict[str, Any] = {}
                for field in ID_FIELDS:
                    value = fields.get(field)
                    items = value if isinstance(value, list) else [value]
                    if any(isinstance(item, str) and REFERENCE.fullmatch(item) for item in items):
                        deferred[field] = value
                        fields.pop(field)
                display = await self.describe_action(step["tool"], fields)
                for field, value in deferred.items():
                    items = value if isinstance(value, list) else [value]
                    labels = []
                    for item in items:
                        match = REFERENCE.fullmatch(item) if isinstance(item, str) else None
                        if match:
                            labels.append(planned[match[1]])
                        else:
                            resolved = await self.describe_action(
                                step["tool"], {field: [item] if isinstance(value, list) else item}
                            )
                            label = resolved[field]
                            labels.extend(label if isinstance(label, list) else [label])
                    display[field] = labels if isinstance(value, list) else labels[0]
                steps.append({**step, "display": display})
                planned[step["id"]] = (
                    step["args"].get("title") or step["args"].get("name") or "Новый объект"
                )
            return {"steps": steps}
        display: dict[str, Any] = {}
        async with self._session_factory() as session:
            repository = BoardRepository(session)
            context = AssistantRepository(session)
            if not await repository.project_member_exists(
                project_id=self.project_id, user_id=self.user_id
            ):
                raise ValueError("Project access is no longer available")
            entity_fields: dict[str, Literal["task", "column", "tag"]] = {
                "task_id": "task",
                "column_id": "column",
                "new_column_id": "column",
                "before_column_id": "column",
                "tag_id": "tag",
            }
            for field, kind in entity_fields.items():
                value = args.get(field)
                if value is not None:
                    label = await context.entity_label(kind, self.project_id, value)
                    display[field] = label or "Не найдено в проекте"
            if args.get("assignee_id") is not None:
                members = await context.project_users(self.project_id)
                member = next((user for user in members if user.id == args["assignee_id"]), None)
                display["assignee_id"] = (
                    (member.full_name or member.username) if member else "Не найден в проекте"
                )
            if args.get("tag_ids"):
                tags = {tag.id: tag.name for tag in await context.project_tags(self.project_id)}
                display["tag_ids"] = [
                    tags.get(tag_id, "Не найден в проекте") for tag_id in args["tag_ids"]
                ]
        return display
