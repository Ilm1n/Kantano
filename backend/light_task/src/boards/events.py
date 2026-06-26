from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.boards.repository import BoardRepository
from src.realtimev1.domain_helpers import dump_column, dump_task
from src.realtimev1.events import RealtimeEventType, RealtimeScope
from src.realtimev1.publisher import DomainEventPublisher
from src.shared.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class ColumnCreated(DomainEvent):
    column_id: int


@dataclass(frozen=True, kw_only=True)
class ColumnUpdated(DomainEvent):
    column_id: int


@dataclass(frozen=True, kw_only=True)
class ColumnDeleted(DomainEvent):
    column_id: int


@dataclass(frozen=True, kw_only=True)
class ColumnsReordered(DomainEvent):
    column_ids: list[int]


@dataclass(frozen=True, kw_only=True)
class TaskCreated(DomainEvent):
    task_id: int


@dataclass(frozen=True, kw_only=True)
class TaskMoved(DomainEvent):
    task_id: int
    from_column_id: int
    to_column_id: int


@dataclass(frozen=True, kw_only=True)
class TaskUpdated(DomainEvent):
    task_id: int


@dataclass(frozen=True, kw_only=True)
class TaskDeleted(DomainEvent):
    task_id: int
    column_id: int


class BoardsDomainEventDispatcher:
    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        event_publisher: DomainEventPublisher,
    ) -> None:
        self._session_factory = session_factory
        self._event_publisher = event_publisher

    async def dispatch(self, events: Sequence[DomainEvent]) -> None:
        for event in events:
            if isinstance(event, ColumnCreated):
                await self._publish_column_created(event)
            if isinstance(event, ColumnUpdated):
                await self._publish_column_updated(event)
            if isinstance(event, ColumnDeleted):
                await self._publish_column_deleted(event)
            if isinstance(event, ColumnsReordered):
                await self._publish_columns_reordered(event)
            if isinstance(event, TaskCreated):
                await self._publish_task_created(event)
            if isinstance(event, TaskMoved):
                await self._publish_task_moved(event)
            if isinstance(event, TaskUpdated):
                await self._publish_task_updated(event)
            if isinstance(event, TaskDeleted):
                await self._publish_task_deleted(event)

    async def _publish_column_created(self, event: ColumnCreated) -> None:
        async with self._session_factory() as session:
            repository = BoardRepository(session)
            column = await repository.get_column_with_tasks(event.column_id)
            if column is None or event.actor_user_id is None:
                return

            await self._event_publisher.publish_event(
                event_type=RealtimeEventType.COLUMN_CREATED,
                scope=RealtimeScope.PROJECT,
                actor_user_id=event.actor_user_id,
                project_id=column.project_id,
                payload={"column": dump_column(column)},
                client_mutation_id=event.client_mutation_id,
            )

            await self._publish_project_list_item_updated(
                repository=repository,
                project_id=column.project_id,
                actor_user_id=event.actor_user_id,
                reason=RealtimeEventType.COLUMN_CREATED,
                client_mutation_id=event.client_mutation_id,
            )

    async def _publish_column_updated(self, event: ColumnUpdated) -> None:
        async with self._session_factory() as session:
            repository = BoardRepository(session)
            column = await repository.get_column_with_tasks(event.column_id)
            if column is None or event.actor_user_id is None:
                return

            await self._event_publisher.publish_event(
                event_type=RealtimeEventType.COLUMN_UPDATED,
                scope=RealtimeScope.PROJECT,
                actor_user_id=event.actor_user_id,
                project_id=column.project_id,
                payload={"column": dump_column(column)},
                client_mutation_id=event.client_mutation_id,
            )

            await self._publish_project_list_item_updated(
                repository=repository,
                project_id=column.project_id,
                actor_user_id=event.actor_user_id,
                reason=RealtimeEventType.COLUMN_UPDATED,
                client_mutation_id=event.client_mutation_id,
            )

    async def _publish_column_deleted(self, event: ColumnDeleted) -> None:
        if event.project_id is None or event.actor_user_id is None:
            return

        await self._event_publisher.publish_event(
            event_type=RealtimeEventType.COLUMN_DELETED,
            scope=RealtimeScope.PROJECT,
            actor_user_id=event.actor_user_id,
            project_id=event.project_id,
            payload={"columnId": event.column_id},
            client_mutation_id=event.client_mutation_id,
        )

        async with self._session_factory() as session:
            repository = BoardRepository(session)
            await self._publish_project_list_item_updated(
                repository=repository,
                project_id=event.project_id,
                actor_user_id=event.actor_user_id,
                reason=RealtimeEventType.COLUMN_DELETED,
                client_mutation_id=event.client_mutation_id,
            )

    async def _publish_columns_reordered(self, event: ColumnsReordered) -> None:
        if event.project_id is None or event.actor_user_id is None:
            return

        await self._event_publisher.publish_event(
            event_type=RealtimeEventType.COLUMNS_REORDERED,
            scope=RealtimeScope.PROJECT,
            actor_user_id=event.actor_user_id,
            project_id=event.project_id,
            payload={"columnOrder": event.column_ids},
            client_mutation_id=event.client_mutation_id,
        )

        async with self._session_factory() as session:
            repository = BoardRepository(session)
            await self._publish_project_list_item_updated(
                repository=repository,
                project_id=event.project_id,
                actor_user_id=event.actor_user_id,
                reason=RealtimeEventType.COLUMNS_REORDERED,
                client_mutation_id=event.client_mutation_id,
            )

    async def _publish_task_created(self, event: TaskCreated) -> None:
        async with self._session_factory() as session:
            repository = BoardRepository(session)
            task = await repository.get_task_with_tags(event.task_id)
            if task is None:
                return
            actor_user_id = event.actor_user_id
            if actor_user_id is None:
                actor_user_id = task.author_id
            if actor_user_id is None:
                return

            await self._event_publisher.publish_event(
                event_type=RealtimeEventType.TASK_CREATED,
                scope=RealtimeScope.PROJECT,
                actor_user_id=actor_user_id,
                project_id=task.project_id,
                payload={"task": dump_task(task)},
                client_mutation_id=event.client_mutation_id,
            )

            affected_user_ids = await repository.get_project_member_user_ids(task.project_id)
            if not affected_user_ids:
                return

            project_updated_at = await repository.get_project_updated_at(task.project_id)
            await self._event_publisher.publish_event(
                event_type=RealtimeEventType.PROJECT_LIST_ITEM_UPDATED,
                scope=RealtimeScope.USER,
                actor_user_id=actor_user_id,
                user_ids=affected_user_ids,
                project_id=task.project_id,
                payload={
                    "projectId": task.project_id,
                    "updatedAt": project_updated_at,
                    "reason": str(RealtimeEventType.TASK_CREATED),
                },
                client_mutation_id=event.client_mutation_id,
            )

    async def _publish_task_updated(self, event: TaskUpdated) -> None:
        async with self._session_factory() as session:
            repository = BoardRepository(session)
            task = await repository.get_task_with_tags(event.task_id)
            if task is None or event.actor_user_id is None:
                return

            await self._event_publisher.publish_event(
                event_type=RealtimeEventType.TASK_UPDATED,
                scope=RealtimeScope.PROJECT,
                actor_user_id=event.actor_user_id,
                project_id=task.project_id,
                payload={"task": dump_task(task)},
                client_mutation_id=event.client_mutation_id,
            )

            await self._publish_project_list_item_updated(
                repository=repository,
                project_id=task.project_id,
                actor_user_id=event.actor_user_id,
                reason=RealtimeEventType.TASK_UPDATED,
                client_mutation_id=event.client_mutation_id,
            )

    async def _publish_task_deleted(self, event: TaskDeleted) -> None:
        if event.project_id is None or event.actor_user_id is None:
            return

        await self._event_publisher.publish_event(
            event_type=RealtimeEventType.TASK_DELETED,
            scope=RealtimeScope.PROJECT,
            actor_user_id=event.actor_user_id,
            project_id=event.project_id,
            payload={"taskId": event.task_id, "columnId": event.column_id},
            client_mutation_id=event.client_mutation_id,
        )

        async with self._session_factory() as session:
            repository = BoardRepository(session)
            await self._publish_project_list_item_updated(
                repository=repository,
                project_id=event.project_id,
                actor_user_id=event.actor_user_id,
                reason=RealtimeEventType.TASK_DELETED,
                client_mutation_id=event.client_mutation_id,
            )

    async def _publish_project_list_item_updated(
        self,
        *,
        repository: BoardRepository,
        project_id: int,
        actor_user_id: int,
        reason: RealtimeEventType,
        client_mutation_id: str | None,
    ) -> None:
        affected_user_ids = await repository.get_project_member_user_ids(project_id)
        if not affected_user_ids:
            return

        project_updated_at = await repository.get_project_updated_at(project_id)
        await self._event_publisher.publish_event(
            event_type=RealtimeEventType.PROJECT_LIST_ITEM_UPDATED,
            scope=RealtimeScope.USER,
            actor_user_id=actor_user_id,
            user_ids=affected_user_ids,
            project_id=project_id,
            payload={
                "projectId": project_id,
                "updatedAt": project_updated_at,
                "reason": str(reason),
            },
            client_mutation_id=client_mutation_id,
        )

    async def _publish_task_moved(self, event: TaskMoved) -> None:
        async with self._session_factory() as session:
            repository = BoardRepository(session)
            task = await repository.get_task_with_tags(event.task_id)
            if task is None or event.actor_user_id is None:
                return

            await self._event_publisher.publish_event(
                event_type=RealtimeEventType.TASK_MOVED,
                scope=RealtimeScope.PROJECT,
                actor_user_id=event.actor_user_id,
                project_id=task.project_id,
                payload={
                    "task": dump_task(task),
                    "fromColumnId": event.from_column_id,
                    "toColumnId": event.to_column_id,
                },
                client_mutation_id=event.client_mutation_id,
            )

            affected_user_ids = await repository.get_project_member_user_ids(task.project_id)
            if not affected_user_ids:
                return

            project_updated_at = await repository.get_project_updated_at(task.project_id)
            await self._event_publisher.publish_event(
                event_type=RealtimeEventType.PROJECT_LIST_ITEM_UPDATED,
                scope=RealtimeScope.USER,
                actor_user_id=event.actor_user_id,
                user_ids=affected_user_ids,
                project_id=task.project_id,
                payload={
                    "projectId": task.project_id,
                    "updatedAt": project_updated_at,
                    "reason": str(RealtimeEventType.TASK_MOVED),
                },
                client_mutation_id=event.client_mutation_id,
            )
