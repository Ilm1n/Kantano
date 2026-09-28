from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.boards.constants import TaskPriority


@dataclass(frozen=True, kw_only=True)
class CreateColumnCommand:
    project_id: int
    actor_user_id: int
    name: str
    tasks_limit: int | None
    client_mutation_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class UpdateColumnCommand:
    project_id: int
    column_id: int
    actor_user_id: int
    changes: dict[str, Any]
    client_mutation_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class DeleteColumnCommand:
    project_id: int
    column_id: int
    actor_user_id: int
    client_mutation_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class ReorderColumnsCommand:
    project_id: int
    actor_user_id: int
    column_ids: list[int]
    client_mutation_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class GetProjectBoardQuery:
    project_id: int
    actor_user_id: int


@dataclass(frozen=True, kw_only=True)
class ListProjectTasksQuery:
    project_id: int
    actor_user_id: int
    assignee_id: int | None = None
    tag_ids: list[int] | None = None
    search: str | None = None


@dataclass(frozen=True, kw_only=True)
class GetTaskDetailsQuery:
    task_id: int
    actor_user_id: int


@dataclass(frozen=True, kw_only=True)
class CreateTaskCommand:
    project_id: int
    column_id: int
    author_id: int
    title: str
    description: str | None
    priority: TaskPriority | None
    assignee_id: int | None
    deadline_at: datetime | None
    tag_ids: list[int] = field(default_factory=list)
    client_mutation_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class MoveTaskCommand:
    task_id: int
    actor_user_id: int
    new_column_id: int
    after_task_id: int | None = None
    client_mutation_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class UpdateTaskCommand:
    task_id: int
    actor_user_id: int
    changes: dict[str, Any]
    tag_ids: list[int] | None = None
    add_tag_id: int | None = None
    remove_tag_id: int | None = None
    client_mutation_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class DeleteTaskCommand:
    task_id: int
    actor_user_id: int
    client_mutation_id: str | None = None
