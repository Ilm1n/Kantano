from typing import Annotated

from fastapi import APIRouter, Depends, status

from src.auth.dependencies import get_current_user
from src.auth.schemas import UserPayload
from src.db.database import db_helper
from src.db.unit_of_work import UnitOfWork
from src.invitations.dto import (
    AcceptInvitationCommand,
    CreateInvitationCommand,
    DeleteInvitationCommand,
    ListProjectInvitationsQuery,
)
from src.invitations.events import InvitationsDomainEventDispatcher
from src.invitations.schemas import (
    InvitationAcceptResponse,
    InvitationCreate,
    InvitationRead,
)
from src.invitations.use_cases import (
    AcceptInvitationUseCase,
    CreateInvitationUseCase,
    DeleteInvitationUseCase,
    ListProjectInvitationsUseCase,
)
from src.realtimev1.dependencies import get_client_mutation_id, get_event_publisher
from src.realtimev1.publisher import DomainEventPublisher

router = APIRouter(tags=["Invitations"])


def get_list_project_invitations_use_case() -> ListProjectInvitationsUseCase:
    return ListProjectInvitationsUseCase(db_helper.async_session_maker)


def get_create_invitation_use_case(
    event_publisher: Annotated[DomainEventPublisher, Depends(get_event_publisher)],
) -> CreateInvitationUseCase:
    dispatcher = InvitationsDomainEventDispatcher(
        db_helper.async_session_maker,
        event_publisher,
    )
    return CreateInvitationUseCase(lambda: UnitOfWork(event_dispatcher=dispatcher))


def get_delete_invitation_use_case(
    event_publisher: Annotated[DomainEventPublisher, Depends(get_event_publisher)],
) -> DeleteInvitationUseCase:
    dispatcher = InvitationsDomainEventDispatcher(
        db_helper.async_session_maker,
        event_publisher,
    )
    return DeleteInvitationUseCase(lambda: UnitOfWork(event_dispatcher=dispatcher))


def get_accept_invitation_use_case(
    event_publisher: Annotated[DomainEventPublisher, Depends(get_event_publisher)],
) -> AcceptInvitationUseCase:
    dispatcher = InvitationsDomainEventDispatcher(
        db_helper.async_session_maker,
        event_publisher,
    )
    return AcceptInvitationUseCase(lambda: UnitOfWork(event_dispatcher=dispatcher))


@router.post(
    "/projects/{project_id}/invite",
    response_model=InvitationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_invitation(
    project_id: int,
    invite_in: InvitationCreate,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[CreateInvitationUseCase, Depends(get_create_invitation_use_case)],
    client_mutation_id: Annotated[str | None, Depends(get_client_mutation_id)],
):
    command = CreateInvitationCommand(
        project_id=project_id,
        inviter_id=current_user.sub,
        role=invite_in.role,
        email=str(invite_in.email) if invite_in.email is not None else None,
        max_uses=invite_in.max_uses,
        expires_in_days=invite_in.expires_in_days,
        client_mutation_id=client_mutation_id,
    )
    return await use_case.execute(command)


@router.get("/projects/{project_id}/invitations", response_model=list[InvitationRead])
async def get_project_invitations(
    project_id: int,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[
        ListProjectInvitationsUseCase,
        Depends(get_list_project_invitations_use_case),
    ],
):
    query = ListProjectInvitationsQuery(
        project_id=project_id,
        actor_user_id=current_user.sub,
    )
    return await use_case.execute(query)


@router.delete(
    "/projects/{project_id}/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "Invitation not found"}},
)
async def delete_invitation(
    project_id: int,
    invitation_id: int,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[DeleteInvitationUseCase, Depends(get_delete_invitation_use_case)],
    client_mutation_id: Annotated[str | None, Depends(get_client_mutation_id)],
):
    command = DeleteInvitationCommand(
        invitation_id=invitation_id,
        project_id=project_id,
        actor_user_id=current_user.sub,
        client_mutation_id=client_mutation_id,
    )
    await use_case.execute(command)


@router.post(
    "/invitations/{token}/accept",
    response_model=InvitationAcceptResponse,
)
async def accept_invitation(
    token: str,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[AcceptInvitationUseCase, Depends(get_accept_invitation_use_case)],
    client_mutation_id: Annotated[str | None, Depends(get_client_mutation_id)],
):
    command = AcceptInvitationCommand(
        token=token,
        user_id=current_user.sub,
        user_email=current_user.email,
        client_mutation_id=client_mutation_id,
    )
    return await use_case.execute(command)
