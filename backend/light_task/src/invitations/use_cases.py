from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.unit_of_work import UnitOfWork
from src.errors import ErrorCode, SuccessCode
from src.invitations.dto import (
    AcceptInvitationCommand,
    CreateInvitationCommand,
    DeleteInvitationCommand,
    ListProjectInvitationsQuery,
)
from src.invitations.events import (
    InvitationAccepted,
    InvitationCreated,
    InvitationDeleted,
)
from src.invitations.models import ProjectInvitation
from src.invitations.permissions import InvitationPermissions
from src.invitations.repository import InvitationRepository
from src.invitations.schemas import InvitationAcceptResponse, SuccessPayload
from src.logger import invitation_logger
from src.projects.models import ProjectMember
from src.shared.errors import (
    AppError,
    DatabaseError,
    ForbiddenError,
    GoneError,
    NotFoundError,
)


class ListProjectInvitationsUseCase:
    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        permissions: InvitationPermissions | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._permissions = permissions or InvitationPermissions()

    async def execute(
        self,
        query: ListProjectInvitationsQuery,
    ) -> list[ProjectInvitation]:
        try:
            async with self._session_factory() as session:
                repository = InvitationRepository(session)
                member = await repository.get_project_member(
                    project_id=query.project_id,
                    user_id=query.actor_user_id,
                )
                self._permissions.ensure_can_manage_invitations(member=member)
                return await repository.list_project_invitations(query.project_id)
        except AppError:
            raise
        except Exception as exc:
            invitation_logger.exception(
                "Failed to list invitations for project %s",
                query.project_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class CreateInvitationUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        permissions: InvitationPermissions | None = None,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._permissions = permissions or InvitationPermissions()
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))

    async def execute(self, command: CreateInvitationCommand) -> ProjectInvitation:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = InvitationRepository(uow.session)
                inviter_member = await repository.get_project_member(
                    project_id=command.project_id,
                    user_id=command.inviter_id,
                )
                self._permissions.ensure_can_manage_invitations(member=inviter_member)
                if inviter_member is None:
                    raise RuntimeError("Invitation permissions returned unexpectedly")
                self._permissions.ensure_can_create_role(
                    member=inviter_member,
                    role=command.role,
                )

                invitation = ProjectInvitation(
                    token=self._token_factory(),
                    project_id=command.project_id,
                    inviter_id=command.inviter_id,
                    role=command.role,
                    email=command.email,
                    max_uses=command.max_uses,
                    expires_at=datetime.now(timezone.utc) + timedelta(days=command.expires_in_days),
                )
                repository.add_invitation(invitation)
                await repository.touch_project(command.project_id)
                await repository.flush()

                uow.collect_event(
                    InvitationCreated(
                        invitation=invitation,
                        actor_user_id=command.inviter_id,
                        project_id=command.project_id,
                        client_mutation_id=command.client_mutation_id,
                    )
                )
                return invitation
        except AppError:
            raise
        except Exception as exc:
            invitation_logger.exception(
                "Failed to create invitation for project %s",
                command.project_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class DeleteInvitationUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        permissions: InvitationPermissions | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._permissions = permissions or InvitationPermissions()

    async def execute(self, command: DeleteInvitationCommand) -> None:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = InvitationRepository(uow.session)
                actor_member = await repository.get_project_member(
                    project_id=command.project_id,
                    user_id=command.actor_user_id,
                )
                self._permissions.ensure_can_manage_invitations(member=actor_member)

                invitation = await repository.get_invitation(
                    invitation_id=command.invitation_id,
                    project_id=command.project_id,
                )
                if invitation is None:
                    raise NotFoundError(ErrorCode.INVITATION_NOT_FOUND)

                await repository.delete_invitation(invitation)
                await repository.touch_project(command.project_id)
                await repository.flush()
                uow.collect_event(
                    InvitationDeleted(
                        invitation_id=command.invitation_id,
                        actor_user_id=command.actor_user_id,
                        project_id=command.project_id,
                        client_mutation_id=command.client_mutation_id,
                    )
                )
        except AppError:
            raise
        except Exception as exc:
            invitation_logger.exception(
                "Failed to delete invitation %s",
                command.invitation_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class AcceptInvitationUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
    ) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: AcceptInvitationCommand) -> InvitationAcceptResponse:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = InvitationRepository(uow.session)
                invitation = await repository.get_invitation_by_token_for_update(command.token)
                if invitation is None:
                    raise NotFoundError(ErrorCode.INVITATION_NOT_FOUND)

                if invitation.expires_at < datetime.now(timezone.utc):
                    raise GoneError(ErrorCode.INVITATION_EXPIRED)

                if invitation.max_uses is not None and invitation.used_count >= invitation.max_uses:
                    raise GoneError(ErrorCode.INVITATION_USAGE_LIMIT_REACHED)

                if invitation.email and invitation.email != command.user_email:
                    raise ForbiddenError(ErrorCode.INVITATION_FOR_OTHER_EMAIL)

                existing_member = await repository.get_project_member(
                    project_id=invitation.project_id,
                    user_id=command.user_id,
                )
                if existing_member is not None:
                    return InvitationAcceptResponse(
                        project_id=invitation.project_id,
                        success=SuccessPayload(code=SuccessCode.ALREADY_PROJECT_MEMBER),
                    )

                new_member = ProjectMember(
                    project_id=invitation.project_id,
                    user_id=command.user_id,
                    role=invitation.role,
                )
                repository.add_member(new_member)
                invitation.used_count += 1
                repository.save_invitation(invitation)
                await repository.touch_project(invitation.project_id)
                await repository.flush()
                affected_user_ids = await repository.get_project_member_user_ids(
                    invitation.project_id
                )
                uow.collect_event(
                    InvitationAccepted(
                        user_id=command.user_id,
                        role=new_member.role,
                        affected_user_ids=affected_user_ids,
                        actor_user_id=command.user_id,
                        project_id=invitation.project_id,
                        client_mutation_id=command.client_mutation_id,
                    )
                )
                return InvitationAcceptResponse(
                    project_id=invitation.project_id,
                    success=SuccessPayload(code=SuccessCode.INVITATION_ACCEPT_SUCCESS),
                )
        except AppError:
            raise
        except Exception as exc:
            invitation_logger.exception(
                "Failed to accept invitation for user %s",
                command.user_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc
