from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from src.assistant.plans import ExecutePlan, validate_plan
from src.boards.constants import TaskPriority
from src.constants import HEX_COLOR_PATTERN


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

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(cls, value: Any) -> Any:
        return normalize_priority(value)


class UpdateTask(BaseModel):
    """Propose updating fields of one task. The user must confirm before execution."""

    task_id: int
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    priority: TaskPriority | None = None
    assignee_id: int | None = None
    deadline_at: datetime | None = None
    tag_ids: list[int] | None = Field(
        default=None,
        description="Replace all task tags only when explicitly requested; use AddTagToTask or RemoveTagFromTask for one tag",
    )

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(cls, value: Any) -> Any:
        return normalize_priority(value)


class MoveTask(BaseModel):
    """Propose moving one task to an existing board column. Requires confirmation."""

    task_id: int
    new_column_id: int


class CreateColumn(BaseModel):
    """Propose creating one board column at the end. Requires confirmation."""

    name: str = Field(min_length=1, max_length=100)


class RenameColumn(BaseModel):
    """Propose renaming an existing column. Requires confirmation."""

    column_id: int
    new_name: str = Field(min_length=1, max_length=100)


class MoveColumn(BaseModel):
    """Move a column before another column, or to the end when before_column_id is null."""

    column_id: int
    before_column_id: int | None = Field(
        description="Destination column ID, or null to place the column last"
    )


class CreateTag(BaseModel):
    """Propose creating a project tag. Requires confirmation."""

    name: str = Field(min_length=1, max_length=50)
    color: str = Field(default="#9CA3AF", pattern=HEX_COLOR_PATTERN)


class UpdateTag(BaseModel):
    """Propose renaming a tag and/or changing its color. Requires confirmation."""

    tag_id: int
    name: str | None = Field(default=None, min_length=1, max_length=50)
    color: str | None = Field(default=None, pattern=HEX_COLOR_PATTERN)


class AddTagToTask(BaseModel):
    """Add one existing project tag to one task without removing other tags."""

    task_id: int
    tag_id: int


class RemoveTagFromTask(BaseModel):
    """Remove one project tag from one task without changing other tags."""

    task_id: int
    tag_id: int


TOOL_SCHEMAS: list[type[BaseModel]] = [
    ProjectOverview,
    SearchTasks,
    GetTask,
    CreateTask,
    UpdateTask,
    MoveTask,
    CreateColumn,
    RenameColumn,
    MoveColumn,
    CreateTag,
    UpdateTag,
    AddTagToTask,
    RemoveTagFromTask,
    ExecutePlan,
]
WRITE_TOOLS = {
    "CreateTask",
    "UpdateTask",
    "MoveTask",
    "CreateColumn",
    "RenameColumn",
    "MoveColumn",
    "CreateTag",
    "UpdateTag",
    "AddTagToTask",
    "RemoveTagFromTask",
}


def normalize_priority(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    aliases = {
        "низкий": "LOW",
        "средний": "MEDIUM",
        "высокий": "HIGH",
        "критический": "CRITICAL",
    }
    return aliases.get(value.strip().lower(), value.strip().upper())


def validate_write(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "ExecutePlan":
        return validate_plan(args, validate_write)
    schema = next(schema for schema in TOOL_SCHEMAS if schema.__name__ == name)
    return schema.model_validate(args).model_dump(mode="json", exclude_unset=True)
