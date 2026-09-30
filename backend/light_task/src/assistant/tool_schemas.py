from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from src.assistant.plans import ExecutePlan, validate_plan
from src.boards.constants import TaskPriority
from src.constants import HEX_COLOR_PATTERN


class ProjectOverview(BaseModel):
    """Read project details, ordered columns with task counts, members (IDs and
    names), and tags (IDs, names, colors). Use to resolve columns, assignees or tags.
    No arguments. For individual tasks use SearchTasks.
    """


class SearchTasks(BaseModel):
    """List current project tasks. All filters are optional; {} lists tasks without
    knowing their IDs or names. Returns IDs, titles, column/assignee names, priorities,
    deadlines, tags, updated_at and the first 300 description characters with
    description_truncated. Read GetTask for full descriptions. Most recently updated
    tasks come first. Continue using next_offset and the same filters/limit when
    more results are needed; null next_offset means the end. Not an edit history.
    """

    search: str | None = Field(
        default=None,
        description="Optional text matched in title or full description; omit to list all tasks",
    )
    assignee_id: int | None = Field(
        default=None,
        description="Filter by member ID from ProjectOverview; omit to include assigned and unassigned tasks",
    )
    tag_id: int | None = Field(
        default=None,
        description="Filter by tag ID from ProjectOverview; omit to include tasks with or without tags",
    )
    limit: int = Field(default=30, ge=1, le=30, description="Maximum tasks per page (1 to 30)")
    offset: int = Field(
        default=0,
        ge=0,
        description="Start at 0; use next_offset from the previous response to read the next page",
    )


class GetTask(BaseModel):
    """Read one task's full description, column/assignee names, priority, deadline,
    tags and updated_at. Use when a search preview is insufficient. Not an edit history.
    """

    task_id: int = Field(description="Existing task ID from SearchTasks in the current project")


class SelectTaskReferences(BaseModel):
    """Select clickable links only for tasks explicitly included in the final
    answer as results of the user's request. Use IDs from the supplied candidates.
    Tasks inspected during search are not answer results. For 'find one task',
    select only the task named in the answer. Counts, general summaries, questions
    and answers without specific matching tasks need an empty list. Return IDs in
    answer order. Do not change or rewrite the answer.
    """

    task_ids: list[int] = Field(
        max_length=30,
        description="IDs of answer results only, in display order; not search candidates",
    )


class CreateTask(BaseModel):
    """Propose one new task in a column. Returns task_id and title after execution.
    For dependencies on a new column or tag, use creation steps in ExecutePlan.
    """

    title: str = Field(min_length=1, max_length=200, description="Short task title")
    column_id: int = Field(description="ID of an existing column from ProjectOverview")
    description: str | None = Field(default=None, description="Task details; omit if not requested")
    priority: TaskPriority | None = Field(
        default=None, description="LOW, MEDIUM, HIGH or CRITICAL; omit if not requested"
    )
    assignee_id: int | None = Field(
        default=None,
        description="Project member ID from ProjectOverview; omit for an unassigned task",
    )
    deadline_at: datetime | None = Field(
        default=None,
        description="ISO 8601 deadline based on the supplied current time; omit if not requested",
    )
    tag_ids: list[int] = Field(
        default_factory=list,
        description="Existing project tag IDs from ProjectOverview; empty list means no tags",
    )

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(cls, value: Any) -> Any:
        return normalize_priority(value)


class UpdateTask(BaseModel):
    """Propose updating one task after reading its current state. Omitted fields
    stay unchanged. Use MoveTask for its column, AddTagToTask/RemoveTagFromTask for
    one tag. Returns task_id and title after execution.
    """

    task_id: int = Field(description="Existing task ID from SearchTasks or GetTask")
    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="New nonempty title; omit to keep the title",
    )
    description: str | None = Field(
        default=None, description="New full description, null to clear it; omit to keep it"
    )
    priority: TaskPriority | None = Field(
        default=None,
        description="New LOW, MEDIUM, HIGH or CRITICAL; null to clear; omit to keep it",
    )
    assignee_id: int | None = Field(
        default=None,
        description="Member ID from ProjectOverview, null to unassign; omit to keep the assignee",
    )
    deadline_at: datetime | None = Field(
        default=None, description="New ISO 8601 deadline, null to clear; omit to keep it"
    )
    tag_ids: list[int] | None = Field(
        default=None,
        description="Replace ALL tags with these project tag IDs only if requested; [] clears them, omit keeps them",
    )

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(cls, value: Any) -> Any:
        return normalize_priority(value)


class MoveTask(BaseModel):
    """Propose moving one task to an existing column in this project.
    Returns task_id and title after execution.
    """

    task_id: int = Field(description="Existing task ID from SearchTasks or GetTask")
    new_column_id: int = Field(description="Destination column ID from ProjectOverview")


class CreateColumn(BaseModel):
    """Propose creating a board column at the end. Returns column_id and name
    after execution; use MoveColumn to reorder it.
    """

    name: str = Field(min_length=1, max_length=100, description="Name of the new column")


class RenameColumn(BaseModel):
    """Propose renaming a column, keeping its tasks. Returns column_id and name
    after execution.
    """

    column_id: int = Field(description="Existing column ID from ProjectOverview")
    new_name: str = Field(min_length=1, max_length=100, description="New column name")


class MoveColumn(BaseModel):
    """Propose reordering a column with its tasks, using the order in ProjectOverview.
    Does not move tasks between columns. Returns column_id and name after execution.
    """

    column_id: int = Field(description="ID of the column to move, from ProjectOverview")
    before_column_id: int | None = Field(
        description="Place before this project column (to its left), or null to place last"
    )


class CreateTag(BaseModel):
    """Propose a project tag after checking existing names with ProjectOverview.
    Returns tag_id and name after execution. Does not attach it to tasks; use
    AddTagToTask or CreateTask in ExecutePlan for creation and attachment.
    """

    name: str = Field(
        min_length=1, max_length=50, description="New tag name, unique within the project"
    )
    color: str = Field(
        default="#9CA3AF",
        pattern=HEX_COLOR_PATTERN,
        description="Six-digit HEX color, e.g. #0000FF for blue; default is gray",
    )


class UpdateTag(BaseModel):
    """Propose renaming a tag and/or changing its color everywhere it is used
    in the project. Supply at least one change; omitted fields stay unchanged.
    Returns tag_id and name after execution.
    """

    tag_id: int = Field(description="Existing project tag ID from ProjectOverview")
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="New nonempty tag name; omit to keep it",
    )
    color: str | None = Field(
        default=None,
        pattern=HEX_COLOR_PATTERN,
        description="New six-digit HEX color; omit to keep it",
    )


class AddTagToTask(BaseModel):
    """Propose attaching one existing tag to a task, preserving other tags.
    For a new tag, use CreateTag then attachment in ExecutePlan.
    Returns task_id and title after execution.
    """

    task_id: int = Field(description="Existing task ID from SearchTasks or GetTask")
    tag_id: int = Field(description="Existing project tag ID from ProjectOverview")


class RemoveTagFromTask(BaseModel):
    """Propose detaching one tag from a task, preserving other tags. Does not
    delete the tag from the project or other tasks. Returns task_id and title after execution.
    """

    task_id: int = Field(description="Existing task ID from SearchTasks or GetTask")
    tag_id: int = Field(description="ID of the tag to detach, from GetTask or ProjectOverview")


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
