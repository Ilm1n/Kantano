from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from src.assistant.dto import ProjectScope
from src.assistant.queries import AssistantProjectQueries
from src.assistant.tool_schemas import (
    WRITE_TOOLS,
    AddTagToTask,
    CreateColumn,
    CreateTag,
    CreateTask,
    MoveColumn,
    MoveTask,
    RemoveTagFromTask,
    RenameColumn,
    UpdateTag,
    UpdateTask,
)
from src.boards.dto import (
    CreateColumnCommand,
    CreateTaskCommand,
    MoveColumnCommand,
    MoveTaskCommand,
    UpdateColumnCommand,
    UpdateTaskCommand,
)
from src.boards.use_cases import (
    CreateColumnUseCase,
    CreateTaskUseCase,
    MoveColumnUseCase,
    MoveTaskUseCase,
    UpdateColumnUseCase,
    UpdateTaskUseCase,
)
from src.db.unit_of_work import UnitOfWork
from src.observability.metrics import record_assistant_tool
from src.tags.dto import CreateTagCommand, UpdateTagCommand
from src.tags.use_cases import CreateTagUseCase, UpdateTagUseCase

logger = logging.getLogger(__name__)


class AssistantTools:
    def __init__(
        self,
        scope: ProjectScope,
        queries: AssistantProjectQueries,
        board_uow_factory: Callable[[], UnitOfWork],
        tag_uow_factory: Callable[[], UnitOfWork],
    ) -> None:
        self.project_id = scope.project_id
        self.user_id = scope.user_id
        self._queries = queries
        self._board_uow_factory = board_uow_factory
        self._tag_uow_factory = tag_uow_factory

    async def read(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        return await self._record_call(name, lambda: self._queries.read(name, args))

    async def _record_call(
        self,
        name: str,
        call: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        # Unknown model-generated names must not create arbitrary metric series.
        tool = (
            name
            if name in WRITE_TOOLS | {"ProjectOverview", "SearchTasks", "GetTask"}
            else "unknown"
        )
        result = "error"
        try:
            value = await call()
            result = "success"
            return value
        finally:
            record_assistant_tool(tool, result)
            logger.info("assistant_tool_call", extra={"tool": tool, "result": result})

    async def describe_action(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        return await self._queries.describe_action(name, args)

    async def execute_write(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        return await self._record_call(name, lambda: self._execute_write(name, args))

    async def _execute_write(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        # The API must atomically claim pending -> executing before calling here.
        if name == "CreateColumn":
            data = CreateColumn.model_validate(args)
            column = await CreateColumnUseCase(self._board_uow_factory).execute(
                CreateColumnCommand(
                    project_id=self.project_id,
                    actor_user_id=self.user_id,
                    name=data.name,
                    tasks_limit=None,
                )
            )
            return {"column_id": column.id, "name": column.name, "kind": "column_created"}

        if name == "RenameColumn":
            data = RenameColumn.model_validate(args)
            column = await UpdateColumnUseCase(self._board_uow_factory).execute(
                UpdateColumnCommand(
                    project_id=self.project_id,
                    column_id=data.column_id,
                    actor_user_id=self.user_id,
                    changes={"name": data.new_name},
                )
            )
            return {"column_id": column.id, "name": column.name, "kind": "column_renamed"}

        if name == "MoveColumn":
            data = MoveColumn.model_validate(args)
            column = await MoveColumnUseCase(self._board_uow_factory).execute(
                MoveColumnCommand(
                    project_id=self.project_id,
                    actor_user_id=self.user_id,
                    column_id=data.column_id,
                    before_column_id=data.before_column_id,
                )
            )
            return {"column_id": column.id, "name": column.name, "kind": "column_moved"}

        if name == "CreateTag":
            data = CreateTag.model_validate(args)
            tag = await CreateTagUseCase(self._tag_uow_factory).execute(
                CreateTagCommand(
                    project_id=self.project_id,
                    actor_user_id=self.user_id,
                    name=data.name,
                    color=data.color,
                )
            )
            return {"tag_id": tag.id, "name": tag.name, "kind": "tag_created"}

        if name == "UpdateTag":
            data = UpdateTag.model_validate(args)
            changes = data.model_dump(exclude={"tag_id"}, exclude_none=True)
            if not changes:
                raise ValueError("No tag changes were requested")
            tag = await UpdateTagUseCase(self._tag_uow_factory).execute(
                UpdateTagCommand(
                    project_id=self.project_id,
                    tag_id=data.tag_id,
                    actor_user_id=self.user_id,
                    changes=changes,
                )
            )
            return {"tag_id": tag.id, "name": tag.name, "kind": "tag_updated"}

        if name == "CreateTask":
            data = CreateTask.model_validate(args)
            result = await CreateTaskUseCase(self._board_uow_factory).execute(
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
            return {"task_id": result.id, "title": result.title, "kind": "created"}

        if name == "UpdateTask":
            data = UpdateTask.model_validate(args)
            supplied = {key: value for key, value in args.items() if key != "task_id"}
            if not supplied:
                raise ValueError("No changes were requested")
            validated = data.model_dump(exclude_unset=True)
            validated.pop("task_id", None)
            tag_ids = validated.pop("tag_ids", None)
            result = await UpdateTaskUseCase(self._board_uow_factory).execute(
                UpdateTaskCommand(
                    project_id=self.project_id,
                    task_id=data.task_id,
                    actor_user_id=self.user_id,
                    changes=validated,
                    tag_ids=tag_ids,
                )
            )
            return {"task_id": result.id, "title": result.title, "kind": "updated"}
        if name == "MoveTask":
            data = MoveTask.model_validate(args)
            result = await MoveTaskUseCase(self._board_uow_factory).execute(
                MoveTaskCommand(
                    project_id=self.project_id,
                    task_id=data.task_id,
                    actor_user_id=self.user_id,
                    new_column_id=data.new_column_id,
                )
            )
            return {"task_id": result.id, "title": result.title, "kind": "moved"}
        if name in {"AddTagToTask", "RemoveTagFromTask"}:
            data = (AddTagToTask if name == "AddTagToTask" else RemoveTagFromTask).model_validate(
                args
            )
            result = await UpdateTaskUseCase(self._board_uow_factory).execute(
                UpdateTaskCommand(
                    project_id=self.project_id,
                    task_id=data.task_id,
                    actor_user_id=self.user_id,
                    changes={},
                    add_tag_id=data.tag_id if name == "AddTagToTask" else None,
                    remove_tag_id=data.tag_id if name == "RemoveTagFromTask" else None,
                )
            )
            return {
                "task_id": result.id,
                "title": result.title,
                "tag_id": data.tag_id,
                "kind": "tag_added_to_task" if name == "AddTagToTask" else "tag_removed_from_task",
            }
        raise ValueError("Unknown write tool")
