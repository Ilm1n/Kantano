from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from src.realtimev1.domain_helpers import dump_tag
from src.realtimev1.events import RealtimeEventType, RealtimeScope
from src.realtimev1.publisher import DomainEventPublisher
from src.shared.events import DomainEvent
from src.tags.models import Tag
from src.tags.repository import TagRepository


@dataclass(frozen=True, kw_only=True)
class TagCreated(DomainEvent):
    tag: Tag
    affected_user_ids: list[int] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class TagUpdated(DomainEvent):
    tag: Tag
    affected_user_ids: list[int] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class TagDeleted(DomainEvent):
    tag_id: int
    affected_user_ids: list[int] = field(default_factory=list)


class TagsDomainEventDispatcher:
    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        event_publisher: DomainEventPublisher,
    ) -> None:
        self._session_factory = session_factory
        self._event_publisher = event_publisher

    async def dispatch(self, events: Sequence[DomainEvent]) -> None:
        for event in events:
            if isinstance(event, TagCreated):
                await self._publish_tag_created(event)
            if isinstance(event, TagUpdated):
                await self._publish_tag_updated(event)
            if isinstance(event, TagDeleted):
                await self._publish_tag_deleted(event)

    async def _publish_tag_created(self, event: TagCreated) -> None:
        if event.project_id is None or event.actor_user_id is None:
            return

        await self._event_publisher.publish_event(
            event_type=RealtimeEventType.TAG_CREATED,
            scope=RealtimeScope.PROJECT,
            actor_user_id=event.actor_user_id,
            project_id=event.project_id,
            payload={"tag": dump_tag(event.tag)},
            client_mutation_id=event.client_mutation_id,
        )
        await self._publish_project_list_item_updated(
            event=event,
            reason=RealtimeEventType.TAG_CREATED,
        )

    async def _publish_tag_updated(self, event: TagUpdated) -> None:
        if event.project_id is None or event.actor_user_id is None:
            return

        await self._event_publisher.publish_event(
            event_type=RealtimeEventType.TAG_UPDATED,
            scope=RealtimeScope.PROJECT,
            actor_user_id=event.actor_user_id,
            project_id=event.project_id,
            payload={"tag": dump_tag(event.tag)},
            client_mutation_id=event.client_mutation_id,
        )
        await self._publish_project_list_item_updated(
            event=event,
            reason=RealtimeEventType.TAG_UPDATED,
        )

    async def _publish_tag_deleted(self, event: TagDeleted) -> None:
        if event.project_id is None or event.actor_user_id is None:
            return

        await self._event_publisher.publish_event(
            event_type=RealtimeEventType.TAG_DELETED,
            scope=RealtimeScope.PROJECT,
            actor_user_id=event.actor_user_id,
            project_id=event.project_id,
            payload={"tagId": event.tag_id},
            client_mutation_id=event.client_mutation_id,
        )
        await self._publish_project_list_item_updated(
            event=event,
            reason=RealtimeEventType.TAG_DELETED,
        )

    async def _publish_project_list_item_updated(
        self,
        *,
        event: TagCreated | TagUpdated | TagDeleted,
        reason: RealtimeEventType,
    ) -> None:
        if event.project_id is None or event.actor_user_id is None:
            return
        if not event.affected_user_ids:
            return

        async with self._session_factory() as session:
            repository = TagRepository(session)
            project_updated_at = await repository.get_project_updated_at(event.project_id)
            await self._event_publisher.publish_event(
                event_type=RealtimeEventType.PROJECT_LIST_ITEM_UPDATED,
                scope=RealtimeScope.USER,
                actor_user_id=event.actor_user_id,
                user_ids=event.affected_user_ids,
                project_id=event.project_id,
                payload={
                    "projectId": event.project_id,
                    "updatedAt": project_updated_at,
                    "reason": str(reason),
                },
                client_mutation_id=event.client_mutation_id,
            )
