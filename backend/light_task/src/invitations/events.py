from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from src.invitations.models import ProjectInvitation
from src.invitations.repository import InvitationRepository
from src.projects.cache import ProjectReadCache
from src.projects.constants import ProjectRole
from src.realtimev1.domain_helpers import dump_invitation
from src.realtimev1.events import (
    RealtimeAudience,
    RealtimeEventType,
    RealtimeScope,
)
from src.realtimev1.publisher import DomainEventPublisher
from src.shared.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class InvitationCreated(DomainEvent):
    invitation: ProjectInvitation


@dataclass(frozen=True, kw_only=True)
class InvitationDeleted(DomainEvent):
    invitation_id: int


@dataclass(frozen=True, kw_only=True)
class InvitationAccepted(DomainEvent):
    user_id: int
    role: ProjectRole
    affected_user_ids: list[int] = field(default_factory=list)


class InvitationsDomainEventDispatcher:
    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        event_publisher: DomainEventPublisher,
        cache: ProjectReadCache | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._event_publisher = event_publisher
        self._cache = cache

    async def dispatch(self, events: Sequence[DomainEvent]) -> None:
        for event in events:
            if (
                self._cache is not None
                and isinstance(event, InvitationAccepted)
                and event.project_id is not None
            ):
                await self._cache.invalidate_members(event.project_id)
            if isinstance(event, InvitationCreated):
                await self._publish_invitation_created(event)
            if isinstance(event, InvitationDeleted):
                await self._publish_invitation_deleted(event)
            if isinstance(event, InvitationAccepted):
                await self._publish_invitation_accepted(event)

    async def _publish_invitation_created(self, event: InvitationCreated) -> None:
        if event.project_id is None or event.actor_user_id is None:
            return

        await self._event_publisher.publish_event(
            event_type=RealtimeEventType.INVITATION_CREATED,
            scope=RealtimeScope.PROJECT,
            actor_user_id=event.actor_user_id,
            project_id=event.project_id,
            payload={"invitation": dump_invitation(event.invitation)},
            audience=RealtimeAudience.MANAGER,
            client_mutation_id=event.client_mutation_id,
        )
        async with self._session_factory() as session:
            repository = InvitationRepository(session)
            user_ids = await repository.get_project_member_user_ids(event.project_id)
            await self._publish_project_list_item_updated(
                repository=repository,
                project_id=event.project_id,
                actor_user_id=event.actor_user_id,
                user_ids=user_ids,
                reason=RealtimeEventType.INVITATION_CREATED,
                client_mutation_id=event.client_mutation_id,
            )

    async def _publish_invitation_deleted(self, event: InvitationDeleted) -> None:
        if event.project_id is None or event.actor_user_id is None:
            return

        await self._event_publisher.publish_event(
            event_type=RealtimeEventType.INVITATION_DELETED,
            scope=RealtimeScope.PROJECT,
            actor_user_id=event.actor_user_id,
            project_id=event.project_id,
            payload={"invitationId": event.invitation_id},
            audience=RealtimeAudience.MANAGER,
            client_mutation_id=event.client_mutation_id,
        )
        async with self._session_factory() as session:
            repository = InvitationRepository(session)
            user_ids = await repository.get_project_member_user_ids(event.project_id)
            await self._publish_project_list_item_updated(
                repository=repository,
                project_id=event.project_id,
                actor_user_id=event.actor_user_id,
                user_ids=user_ids,
                reason=RealtimeEventType.INVITATION_DELETED,
                client_mutation_id=event.client_mutation_id,
            )

    async def _publish_invitation_accepted(self, event: InvitationAccepted) -> None:
        if event.project_id is None or event.actor_user_id is None:
            return

        await self._event_publisher.publish_event(
            event_type=RealtimeEventType.MEMBER_ADDED,
            scope=RealtimeScope.PROJECT,
            actor_user_id=event.actor_user_id,
            project_id=event.project_id,
            payload={
                "userId": event.user_id,
                "role": event.role,
            },
            client_mutation_id=event.client_mutation_id,
        )
        await self._event_publisher.publish_event(
            event_type=RealtimeEventType.PROJECT_ADDED_TO_USER,
            scope=RealtimeScope.USER,
            actor_user_id=event.actor_user_id,
            user_ids=[event.user_id],
            project_id=event.project_id,
            payload={"projectId": event.project_id},
            client_mutation_id=event.client_mutation_id,
        )
        async with self._session_factory() as session:
            repository = InvitationRepository(session)
            await self._publish_project_list_item_updated(
                repository=repository,
                project_id=event.project_id,
                actor_user_id=event.actor_user_id,
                user_ids=event.affected_user_ids,
                reason=RealtimeEventType.MEMBER_ADDED,
                client_mutation_id=event.client_mutation_id,
            )

    async def _publish_project_list_item_updated(
        self,
        *,
        repository: InvitationRepository,
        project_id: int,
        actor_user_id: int,
        user_ids: list[int],
        reason: RealtimeEventType,
        client_mutation_id: str | None,
    ) -> None:
        if not user_ids:
            return

        project_updated_at = await repository.get_project_updated_at(project_id)
        await self._event_publisher.publish_event(
            event_type=RealtimeEventType.PROJECT_LIST_ITEM_UPDATED,
            scope=RealtimeScope.USER,
            actor_user_id=actor_user_id,
            user_ids=user_ids,
            project_id=project_id,
            payload={
                "projectId": project_id,
                "updatedAt": project_updated_at,
                "reason": str(reason),
            },
            client_mutation_id=client_mutation_id,
        )
