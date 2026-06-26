from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.boards.dto import (
    CreateColumnCommand,
    CreateTaskCommand,
    DeleteColumnCommand,
    DeleteTaskCommand,
    GetProjectBoardQuery,
    GetTaskDetailsQuery,
    ListProjectTasksQuery,
    MoveTaskCommand,
    ReorderColumnsCommand,
    UpdateColumnCommand,
    UpdateTaskCommand,
)
from src.boards.events import (
    ColumnCreated,
    ColumnDeleted,
    ColumnsReordered,
    ColumnUpdated,
    TaskCreated,
    TaskDeleted,
    TaskMoved,
    TaskUpdated,
)
from src.boards.models import BoardColumn, Task
from src.boards.ordering import POSITION_GAP, TaskOrdering
from src.boards.permissions import BoardPermissions
from src.boards.repository import BoardRepository
from src.db.unit_of_work import UnitOfWork
from src.errors import ErrorCode
from src.logger import board_logger
from src.shared.errors import (
    AppError,
    BadRequestError,
    ConflictError,
    DatabaseError,
    NotFoundError,
)


class GetProjectBoardUseCase:
    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        permissions: BoardPermissions | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._permissions = permissions or BoardPermissions()

    async def execute(self, query: GetProjectBoardQuery) -> list[BoardColumn]:
        try:
            async with self._session_factory() as session:
                repository = BoardRepository(session)
                actor_member = await repository.get_project_member(
                    project_id=query.project_id,
                    user_id=query.actor_user_id,
                )
                self._permissions.ensure_project_member_can_read(actor_member=actor_member)
                return await repository.list_project_columns(query.project_id)
        except AppError:
            raise
        except Exception as exc:
            board_logger.exception(
                "Failed to read board for project %s",
                query.project_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class ListProjectTasksUseCase:
    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        permissions: BoardPermissions | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._permissions = permissions or BoardPermissions()

    async def execute(self, query: ListProjectTasksQuery) -> list[Task]:
        try:
            async with self._session_factory() as session:
                repository = BoardRepository(session)
                actor_member = await repository.get_project_member(
                    project_id=query.project_id,
                    user_id=query.actor_user_id,
                )
                self._permissions.ensure_project_member_can_read(actor_member=actor_member)
                return await repository.list_project_tasks(
                    project_id=query.project_id,
                    assignee_id=query.assignee_id,
                    tag_ids=query.tag_ids,
                    search=query.search,
                )
        except AppError:
            raise
        except Exception as exc:
            board_logger.exception(
                "Failed to list tasks for project %s",
                query.project_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class GetTaskDetailsUseCase:
    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        permissions: BoardPermissions | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._permissions = permissions or BoardPermissions()

    async def execute(self, query: GetTaskDetailsQuery) -> Task:
        try:
            async with self._session_factory() as session:
                repository = BoardRepository(session)
                task = await repository.get_task_with_tags(query.task_id)
                if task is None:
                    raise NotFoundError(ErrorCode.TASK_NOT_FOUND)

                actor_member = await repository.get_project_member(
                    project_id=task.project_id,
                    user_id=query.actor_user_id,
                )
                self._permissions.ensure_task_read_allowed(actor_member=actor_member)
                return task
        except AppError:
            raise
        except Exception as exc:
            board_logger.exception(
                "Failed to read task %s",
                query.task_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class CreateColumnUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        permissions: BoardPermissions | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._permissions = permissions or BoardPermissions()

    async def execute(self, command: CreateColumnCommand) -> BoardColumn:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = BoardRepository(uow.session)
                actor_member = await repository.get_project_member(
                    project_id=command.project_id,
                    user_id=command.actor_user_id,
                )
                self._permissions.ensure_can_manage_columns(actor_member=actor_member)

                max_position = await repository.get_max_column_position(command.project_id)
                column = repository.add_column(
                    project_id=command.project_id,
                    name=command.name,
                    tasks_limit=command.tasks_limit,
                    position=max_position + POSITION_GAP,
                )
                await repository.touch_project(command.project_id)
                await repository.flush()

                loaded_column = await repository.get_column_with_tasks(column.id)
                if loaded_column is None:
                    raise DatabaseError()

                uow.collect_event(
                    ColumnCreated(
                        column_id=loaded_column.id,
                        actor_user_id=command.actor_user_id,
                        project_id=command.project_id,
                        client_mutation_id=command.client_mutation_id,
                    )
                )
                return loaded_column
        except AppError:
            raise
        except Exception as exc:
            board_logger.exception(
                "Failed to create column in project %s",
                command.project_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class UpdateColumnUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        permissions: BoardPermissions | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._permissions = permissions or BoardPermissions()

    async def execute(self, command: UpdateColumnCommand) -> BoardColumn:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = BoardRepository(uow.session)
                actor_member = await repository.get_project_member(
                    project_id=command.project_id,
                    user_id=command.actor_user_id,
                )
                self._permissions.ensure_can_manage_columns(actor_member=actor_member)

                column = await repository.get_column_in_project(
                    project_id=command.project_id,
                    column_id=command.column_id,
                )
                if column is None:
                    raise NotFoundError(ErrorCode.COLUMN_NOT_FOUND)

                for key, value in command.changes.items():
                    setattr(column, key, value)

                repository.save_column(column)
                await repository.touch_project(command.project_id)
                await repository.flush()

                updated_column = await repository.get_column_with_tasks(column.id)
                if updated_column is None:
                    raise DatabaseError()

                uow.collect_event(
                    ColumnUpdated(
                        column_id=updated_column.id,
                        actor_user_id=command.actor_user_id,
                        project_id=command.project_id,
                        client_mutation_id=command.client_mutation_id,
                    )
                )
                return updated_column
        except AppError:
            raise
        except Exception as exc:
            board_logger.exception(
                "Failed to update column %s",
                command.column_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class DeleteColumnUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        permissions: BoardPermissions | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._permissions = permissions or BoardPermissions()

    async def execute(self, command: DeleteColumnCommand) -> None:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = BoardRepository(uow.session)
                actor_member = await repository.get_project_member(
                    project_id=command.project_id,
                    user_id=command.actor_user_id,
                )
                self._permissions.ensure_can_manage_columns(actor_member=actor_member)

                column = await repository.get_column_in_project(
                    project_id=command.project_id,
                    column_id=command.column_id,
                )
                if column is None:
                    raise NotFoundError(ErrorCode.COLUMN_NOT_FOUND)

                await repository.delete_column(column)
                await repository.touch_project(command.project_id)
                await repository.flush()

                uow.collect_event(
                    ColumnDeleted(
                        column_id=command.column_id,
                        actor_user_id=command.actor_user_id,
                        project_id=command.project_id,
                        client_mutation_id=command.client_mutation_id,
                    )
                )
        except AppError:
            raise
        except Exception as exc:
            board_logger.exception(
                "Failed to delete column %s",
                command.column_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class ReorderColumnsUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        permissions: BoardPermissions | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._permissions = permissions or BoardPermissions()

    async def execute(self, command: ReorderColumnsCommand) -> None:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = BoardRepository(uow.session)
                actor_member = await repository.get_project_member(
                    project_id=command.project_id,
                    user_id=command.actor_user_id,
                )
                self._permissions.ensure_can_manage_columns(actor_member=actor_member)

                columns = await repository.list_project_columns_by_ids(
                    project_id=command.project_id,
                    column_ids=command.column_ids,
                )
                col_map = {column.id: column for column in columns}
                for index, column_id in enumerate(command.column_ids):
                    column = col_map.get(column_id)
                    if column is None:
                        continue

                    column.position = (index + 1) * POSITION_GAP
                    repository.save_column(column)

                if not columns:
                    return

                await repository.touch_project(command.project_id)
                await repository.flush()
                uow.collect_event(
                    ColumnsReordered(
                        column_ids=command.column_ids,
                        actor_user_id=command.actor_user_id,
                        project_id=command.project_id,
                        client_mutation_id=command.client_mutation_id,
                    )
                )
        except AppError:
            raise
        except Exception as exc:
            board_logger.exception(
                "Failed to reorder columns in project %s",
                command.project_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class CreateTaskUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        permissions: BoardPermissions | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._permissions = permissions or BoardPermissions()

    async def execute(self, command: CreateTaskCommand) -> Task:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = BoardRepository(uow.session)
                column = await repository.get_column(command.column_id)
                if column is None:
                    raise NotFoundError(ErrorCode.COLUMN_NOT_FOUND)

                if column.project_id != command.project_id:
                    raise BadRequestError(ErrorCode.COLUMN_BELONGS_ANOTHER_PROJECT)

                if column.tasks_limit is not None:
                    current_count = await repository.count_tasks_in_column(command.column_id)
                    if current_count >= column.tasks_limit:
                        raise ConflictError(ErrorCode.COLUMN_TASK_LIMIT_REACHED)

                actor_member = await repository.get_project_member(
                    project_id=command.project_id,
                    user_id=command.author_id,
                )
                self._permissions.ensure_task_assignee_allowed(
                    actor_member=actor_member,
                    actor_user_id=command.author_id,
                    assignee_id=command.assignee_id,
                )

                if command.assignee_id is not None:
                    assignee_exists = await repository.project_member_exists(
                        project_id=command.project_id,
                        user_id=command.assignee_id,
                    )
                    if not assignee_exists:
                        raise BadRequestError(ErrorCode.ASSIGNEE_NOT_PROJECT_MEMBER)

                tags = await repository.list_tags_by_ids(
                    project_id=command.project_id,
                    tag_ids=command.tag_ids,
                )
                if len(tags) != len(command.tag_ids):
                    raise BadRequestError(ErrorCode.INVALID_TAG_IDS)

                max_position = await repository.get_max_task_position(command.column_id)
                task = await repository.add_task(
                    title=command.title,
                    description=command.description,
                    priority=command.priority,
                    deadline_at=command.deadline_at,
                    project_id=command.project_id,
                    column_id=command.column_id,
                    assignee_id=command.assignee_id,
                    author_id=command.author_id,
                    position=max_position + POSITION_GAP,
                    tags=tags,
                )
                await repository.touch_project(command.project_id)
                await repository.flush()

                loaded_task = await repository.get_task_with_tags(task.id)
                if loaded_task is None:
                    raise DatabaseError()

                uow.collect_event(
                    TaskCreated(
                        task_id=loaded_task.id,
                        actor_user_id=command.author_id,
                        project_id=command.project_id,
                        client_mutation_id=command.client_mutation_id,
                    )
                )
                return loaded_task
        except AppError:
            raise
        except Exception as exc:
            board_logger.exception(
                "Failed to create task in project %s",
                command.project_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class MoveTaskUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        permissions: BoardPermissions | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._permissions = permissions or BoardPermissions()

    async def execute(self, command: MoveTaskCommand) -> Task:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = BoardRepository(uow.session)
                task = await repository.get_task_for_update(command.task_id)
                if task is None:
                    raise NotFoundError(ErrorCode.TASK_NOT_FOUND)

                actor_member = await repository.get_project_member(
                    project_id=task.project_id,
                    user_id=command.actor_user_id,
                )
                self._permissions.ensure_task_update_allowed(
                    actor_member=actor_member,
                    actor_user_id=command.actor_user_id,
                    task_assignee_id=task.assignee_id,
                )

                from_column_id = task.column_id
                if task.column_id != command.new_column_id:
                    target_column = await repository.get_column(command.new_column_id)
                    if target_column is None or target_column.project_id != task.project_id:
                        raise BadRequestError(ErrorCode.INVALID_TARGET_COLUMN)

                    if target_column.tasks_limit is not None:
                        current_count = await repository.count_tasks_in_column(
                            command.new_column_id
                        )
                        if current_count >= target_column.tasks_limit:
                            raise ConflictError(ErrorCode.COLUMN_TASK_LIMIT_REACHED)

                ordering = TaskOrdering(repository)
                attempts = 0
                while attempts < 2:
                    attempts += 1
                    new_position = await ordering.calculate_new_position(
                        column_id=command.new_column_id,
                        after_task_id=command.after_task_id,
                    )
                    if new_position is None:
                        await ordering.rebalance_column(command.new_column_id)
                        continue

                    task.column_id = command.new_column_id
                    task.position = new_position
                    task.updated_at = datetime.now(UTC)
                    repository.save_task(task)
                    await repository.touch_project(task.project_id)
                    await repository.flush()

                    moved_task = await repository.get_task_with_tags(task.id)
                    if moved_task is None:
                        raise DatabaseError()

                    uow.collect_event(
                        TaskMoved(
                            task_id=moved_task.id,
                            from_column_id=from_column_id,
                            to_column_id=command.new_column_id,
                            actor_user_id=command.actor_user_id,
                            project_id=moved_task.project_id,
                            client_mutation_id=command.client_mutation_id,
                        )
                    )
                    return moved_task

                raise DatabaseError()
        except AppError:
            raise
        except Exception as exc:
            board_logger.exception(
                "Failed to move task %s",
                command.task_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class UpdateTaskUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        permissions: BoardPermissions | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._permissions = permissions or BoardPermissions()

    async def execute(self, command: UpdateTaskCommand) -> Task:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = BoardRepository(uow.session)
                task = await repository.get_task_for_update(command.task_id)
                if task is None:
                    raise NotFoundError(ErrorCode.TASK_NOT_FOUND)

                actor_member = await repository.get_project_member(
                    project_id=task.project_id,
                    user_id=command.actor_user_id,
                )
                self._permissions.ensure_task_update_allowed(
                    actor_member=actor_member,
                    actor_user_id=command.actor_user_id,
                    task_assignee_id=task.assignee_id,
                )

                assignee_id = command.changes.get("assignee_id")
                if (
                    "assignee_id" in command.changes
                    and assignee_id is not None
                    and task.assignee_id != assignee_id
                ):
                    assignee_exists = await repository.project_member_exists(
                        project_id=task.project_id,
                        user_id=assignee_id,
                    )
                    if not assignee_exists:
                        raise BadRequestError(ErrorCode.ASSIGNEE_NOT_PROJECT_MEMBER)

                if command.tag_ids is not None:
                    tags = await repository.list_tags_by_ids(
                        project_id=task.project_id,
                        tag_ids=command.tag_ids,
                    )
                    if len(tags) != len(command.tag_ids):
                        raise BadRequestError(ErrorCode.INVALID_TAG_IDS)
                    task.tags = list(tags)

                for key, value in command.changes.items():
                    setattr(task, key, value)

                task.updated_at = datetime.now(UTC)
                repository.save_task(task)
                await repository.touch_project(task.project_id)
                await repository.flush()

                updated_task = await repository.get_task_with_tags(task.id)
                if updated_task is None:
                    raise DatabaseError()

                uow.collect_event(
                    TaskUpdated(
                        task_id=updated_task.id,
                        actor_user_id=command.actor_user_id,
                        project_id=updated_task.project_id,
                        client_mutation_id=command.client_mutation_id,
                    )
                )
                return updated_task
        except AppError:
            raise
        except Exception as exc:
            board_logger.exception(
                "Failed to update task %s",
                command.task_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class DeleteTaskUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        permissions: BoardPermissions | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._permissions = permissions or BoardPermissions()

    async def execute(self, command: DeleteTaskCommand) -> None:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = BoardRepository(uow.session)
                task = await repository.get_task_for_update(command.task_id)
                if task is None:
                    raise NotFoundError(ErrorCode.TASK_NOT_FOUND)

                actor_member = await repository.get_project_member(
                    project_id=task.project_id,
                    user_id=command.actor_user_id,
                )
                self._permissions.ensure_task_delete_allowed(actor_member=actor_member)

                task_id = task.id
                project_id = task.project_id
                column_id = task.column_id
                await repository.delete_task(task)
                await repository.touch_project(project_id)
                await repository.flush()

                uow.collect_event(
                    TaskDeleted(
                        task_id=task_id,
                        column_id=column_id,
                        actor_user_id=command.actor_user_id,
                        project_id=project_id,
                        client_mutation_id=command.client_mutation_id,
                    )
                )
        except AppError:
            raise
        except Exception as exc:
            board_logger.exception(
                "Failed to delete task %s",
                command.task_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc
