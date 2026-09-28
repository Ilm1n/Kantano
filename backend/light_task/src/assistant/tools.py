from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from src.boards.constants import TaskPriority
from src.boards.dto import CreateTaskCommand, MoveTaskCommand, UpdateTaskCommand
from src.boards.events import BoardsDomainEventDispatcher
from src.boards.models import BoardColumn, Task
from src.boards.repository import BoardRepository
from src.boards.use_cases import CreateTaskUseCase, MoveTaskUseCase, UpdateTaskUseCase
from src.db.database import db_helper
from src.db.unit_of_work import UnitOfWork
from src.projects.cache import ProjectReadCache
from src.projects.models import Project, ProjectMember
from src.realtimev1.publisher import DomainEventPublisher
from src.tags.models import Tag
from src.users.models import User


class ProjectOverview(BaseModel):
    """Read project details, board columns, task counts, members and tags."""


class SearchTasks(BaseModel):
    """Find tasks in the current project by text, assignee or tag."""

    search: str | None = Field(default=None, description="Part of task title or description")
    assignee_id: int | None = None
    tag_id: int | None = None


class GetTask(BaseModel):
    """Read one task by its numeric ID in the current project."""

    task_id: int


class CreateTask(BaseModel):
    """Propose creation of one task. The user must confirm before it is executed."""

    title: str = Field(min_length=1, max_length=200)
    column_id: int = Field(description="ID of an existing column from ProjectOverview")
    description: str | None = None
    priority: TaskPriority | None = None
    assignee_id: int | None = None
    deadline_at: datetime | None = None
    tag_ids: list[int] = Field(default_factory=list)


class UpdateTask(BaseModel):
    """Propose updating fields of one task. The user must confirm before execution."""

    task_id: int
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    priority: TaskPriority | None = None
    assignee_id: int | None = None
    deadline_at: datetime | None = None
    tag_ids: list[int] | None = None


class MoveTask(BaseModel):
    """Propose moving one task to an existing board column. Requires confirmation."""

    task_id: int
    new_column_id: int


TOOL_SCHEMAS: list[type[BaseModel]] = [
    ProjectOverview,
    SearchTasks,
    GetTask,
    CreateTask,
    UpdateTask,
    MoveTask,
]
WRITE_TOOLS = {"CreateTask", "UpdateTask", "MoveTask"}


class AssistantTools:
    def __init__(
        self,
        project_id: int,
        user_id: int,
        event_publisher: DomainEventPublisher,
        cache: ProjectReadCache,
    ) -> None:
        self.project_id = project_id
        self.user_id = user_id
        self.dispatcher = BoardsDomainEventDispatcher(
            db_helper.async_session_maker, event_publisher, cache
        )

    async def read(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        async with db_helper.async_session_maker() as session:
            repository = BoardRepository(session)
            if not await repository.project_member_exists(
                project_id=self.project_id, user_id=self.user_id
            ):
                raise ValueError("Project access is no longer available")
            if name == "ProjectOverview":
                project = await session.get(Project, self.project_id)
                if project is None:
                    raise ValueError("Project no longer exists")
                columns = (
                    await session.scalars(
                        select(BoardColumn)
                        .where(BoardColumn.project_id == self.project_id)
                        .order_by(BoardColumn.position)
                    )
                ).all()
                count_rows = (
                    await session.execute(
                        select(Task.column_id, func.count(Task.id))
                        .where(Task.project_id == self.project_id)
                        .group_by(Task.column_id)
                    )
                ).all()
                counts: dict[int, int] = {column_id: count for column_id, count in count_rows}
                members = (
                    await session.execute(
                        select(User.id, User.username, User.full_name)
                        .join(ProjectMember, ProjectMember.user_id == User.id)
                        .where(ProjectMember.project_id == self.project_id)
                    )
                ).all()
                tags = (
                    await session.scalars(select(Tag).where(Tag.project_id == self.project_id))
                ).all()
                return {
                    "project": {
                        "id": project.id,
                        "name": project.name,
                        "description": project.description,
                    },
                    "columns": [
                        {"id": c.id, "name": c.name, "task_count": counts.get(c.id, 0)}
                        for c in columns
                    ],
                    "members": [
                        {"id": m.id, "username": m.username, "name": m.full_name} for m in members
                    ],
                    "tags": [{"id": t.id, "name": t.name} for t in tags],
                }
            if name == "SearchTasks":
                query = SearchTasks.model_validate(args)
                tasks = await repository.list_project_tasks(
                    project_id=self.project_id,
                    search=query.search,
                    assignee_id=query.assignee_id,
                    tag_ids=[query.tag_id] if query.tag_id else None,
                )
                return {
                    "tasks": [
                        {
                            "id": t.id,
                            "title": t.title,
                            "column_id": t.column_id,
                            "priority": t.priority.value if t.priority else None,
                            "assignee_id": t.assignee_id,
                        }
                        for t in tasks[:30]
                    ],
                    "truncated": len(tasks) > 30,
                }
            if name == "GetTask":
                query = GetTask.model_validate(args)
                task = await repository.get_task_with_tags(query.task_id)
                if task is None or task.project_id != self.project_id:
                    raise ValueError("Task not found in this project")
                return {
                    "id": task.id,
                    "title": task.title,
                    "description": task.description,
                    "column_id": task.column_id,
                    "priority": task.priority.value if task.priority else None,
                    "assignee_id": task.assignee_id,
                    "deadline_at": task.deadline_at.isoformat() if task.deadline_at else None,
                    "tags": [{"id": tag.id, "name": tag.name} for tag in task.tags],
                }
            raise ValueError("Unknown read tool")

    async def execute_write(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        # The API must atomically claim pending -> executing before calling here.
        if name == "CreateTask":
            data = CreateTask.model_validate(args)
            async with db_helper.async_session_maker() as session:
                column = await session.get(BoardColumn, data.column_id)
                if column is None or column.project_id != self.project_id:
                    raise ValueError("Column not found in this project")
            result = await CreateTaskUseCase(
                lambda: UnitOfWork(event_dispatcher=self.dispatcher)
            ).execute(
                CreateTaskCommand(
                    project_id=self.project_id,
                    column_id=data.column_id,
                    author_id=self.user_id,
                    title=data.title,
                    description=data.description,
                    priority=data.priority,
                    assignee_id=data.assignee_id,
                    deadline_at=data.deadline_at,
                    tag_ids=data.tag_ids,
                )
            )
            return {"task_id": result.id, "kind": "created"}

        if name in {"UpdateTask", "MoveTask"}:
            task_id = int(args["task_id"])
            async with db_helper.async_session_maker() as session:
                task = await session.get(Task, task_id)
                if task is None or task.project_id != self.project_id:
                    raise ValueError("Task not found in this project")
        if name == "UpdateTask":
            data = UpdateTask.model_validate(args)
            supplied = {key: value for key, value in args.items() if key != "task_id"}
            if not supplied:
                raise ValueError("No changes were requested")
            validated = data.model_dump(exclude_unset=True)
            validated.pop("task_id", None)
            tag_ids = validated.pop("tag_ids", None)
            result = await UpdateTaskUseCase(
                lambda: UnitOfWork(event_dispatcher=self.dispatcher)
            ).execute(
                UpdateTaskCommand(
                    task_id=data.task_id,
                    actor_user_id=self.user_id,
                    changes=validated,
                    tag_ids=tag_ids,
                )
            )
            return {"task_id": result.id, "kind": "updated"}
        if name == "MoveTask":
            data = MoveTask.model_validate(args)
            async with db_helper.async_session_maker() as session:
                column = await session.get(BoardColumn, data.new_column_id)
                if column is None or column.project_id != self.project_id:
                    raise ValueError("Column not found in this project")
            result = await MoveTaskUseCase(
                lambda: UnitOfWork(event_dispatcher=self.dispatcher)
            ).execute(
                MoveTaskCommand(
                    task_id=data.task_id,
                    actor_user_id=self.user_id,
                    new_column_id=data.new_column_id,
                )
            )
            return {"task_id": result.id, "kind": "moved"}
        raise ValueError("Unknown write tool")
