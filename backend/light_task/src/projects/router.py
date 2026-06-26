from typing import Annotated

from fastapi import APIRouter, Depends, status

from src.auth.dependencies import get_current_user
from src.auth.schemas import UserPayload
from src.db.database import db_helper
from src.db.unit_of_work import UnitOfWork
from src.projects.dto import (
    CreateProjectCommand,
    DeleteProjectCommand,
    GetProjectDetailsQuery,
    ListProjectMembersQuery,
    ListUserProjectsQuery,
    RemoveMemberCommand,
    UpdateMemberRoleCommand,
    UpdateProjectCommand,
)
from src.projects.events import ProjectsDomainEventDispatcher
from src.projects.schemas import (
    ProjectCreate,
    ProjectMemberRead,
    ProjectMemberUpdate,
    ProjectRead,
    ProjectUpdate,
)
from src.projects.use_cases import (
    CreateProjectUseCase,
    DeleteProjectUseCase,
    GetProjectDetailsUseCase,
    ListProjectMembersUseCase,
    ListUserProjectsUseCase,
    RemoveMemberUseCase,
    UpdateMemberRoleUseCase,
    UpdateProjectUseCase,
)
from src.realtimev1.dependencies import get_client_mutation_id, get_event_publisher
from src.realtimev1.publisher import DomainEventPublisher

router = APIRouter(prefix="/projects", tags=["Projects"])


def get_list_user_projects_use_case() -> ListUserProjectsUseCase:
    return ListUserProjectsUseCase(db_helper.async_session_maker)


def get_project_details_use_case() -> GetProjectDetailsUseCase:
    return GetProjectDetailsUseCase(db_helper.async_session_maker)


def get_list_project_members_use_case() -> ListProjectMembersUseCase:
    return ListProjectMembersUseCase(db_helper.async_session_maker)


def get_create_project_use_case(
    event_publisher: Annotated[DomainEventPublisher, Depends(get_event_publisher)],
) -> CreateProjectUseCase:
    dispatcher = ProjectsDomainEventDispatcher(
        db_helper.async_session_maker,
        event_publisher,
    )
    return CreateProjectUseCase(lambda: UnitOfWork(event_dispatcher=dispatcher))


def get_update_project_use_case(
    event_publisher: Annotated[DomainEventPublisher, Depends(get_event_publisher)],
) -> UpdateProjectUseCase:
    dispatcher = ProjectsDomainEventDispatcher(
        db_helper.async_session_maker,
        event_publisher,
    )
    return UpdateProjectUseCase(lambda: UnitOfWork(event_dispatcher=dispatcher))


def get_delete_project_use_case(
    event_publisher: Annotated[DomainEventPublisher, Depends(get_event_publisher)],
) -> DeleteProjectUseCase:
    dispatcher = ProjectsDomainEventDispatcher(
        db_helper.async_session_maker,
        event_publisher,
    )
    return DeleteProjectUseCase(lambda: UnitOfWork(event_dispatcher=dispatcher))


def get_remove_member_use_case(
    event_publisher: Annotated[DomainEventPublisher, Depends(get_event_publisher)],
) -> RemoveMemberUseCase:
    dispatcher = ProjectsDomainEventDispatcher(
        db_helper.async_session_maker,
        event_publisher,
    )
    return RemoveMemberUseCase(lambda: UnitOfWork(event_dispatcher=dispatcher))


def get_update_member_role_use_case(
    event_publisher: Annotated[DomainEventPublisher, Depends(get_event_publisher)],
) -> UpdateMemberRoleUseCase:
    dispatcher = ProjectsDomainEventDispatcher(
        db_helper.async_session_maker,
        event_publisher,
    )
    return UpdateMemberRoleUseCase(lambda: UnitOfWork(event_dispatcher=dispatcher))


@router.post(
    "/",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    project_in: ProjectCreate,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[CreateProjectUseCase, Depends(get_create_project_use_case)],
    client_mutation_id: Annotated[str | None, Depends(get_client_mutation_id)],
):
    command = CreateProjectCommand(
        owner_id=current_user.sub,
        name=project_in.name,
        description=project_in.description,
        color=project_in.color,
        client_mutation_id=client_mutation_id,
    )
    return await use_case.execute(command)


@router.get("/", response_model=list[ProjectRead])
async def get_my_projects(
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[ListUserProjectsUseCase, Depends(get_list_user_projects_use_case)],
):
    query = ListUserProjectsQuery(user_id=current_user.sub)
    return await use_case.execute(query)


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project_details(
    project_id: int,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[GetProjectDetailsUseCase, Depends(get_project_details_use_case)],
):
    query = GetProjectDetailsQuery(
        project_id=project_id,
        actor_user_id=current_user.sub,
    )
    return await use_case.execute(query)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: int,
    project_update: ProjectUpdate,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[UpdateProjectUseCase, Depends(get_update_project_use_case)],
    client_mutation_id: Annotated[str | None, Depends(get_client_mutation_id)],
):
    command = UpdateProjectCommand(
        project_id=project_id,
        actor_user_id=current_user.sub,
        changes=project_update.model_dump(exclude_unset=True),
        client_mutation_id=client_mutation_id,
    )
    return await use_case.execute(command)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: int,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[DeleteProjectUseCase, Depends(get_delete_project_use_case)],
    client_mutation_id: Annotated[str | None, Depends(get_client_mutation_id)],
):
    command = DeleteProjectCommand(
        project_id=project_id,
        actor_user_id=current_user.sub,
        client_mutation_id=client_mutation_id,
    )
    await use_case.execute(command)


@router.get("/{project_id}/members", response_model=list[ProjectMemberRead])
async def get_project_members(
    project_id: int,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[ListProjectMembersUseCase, Depends(get_list_project_members_use_case)],
):
    query = ListProjectMembersQuery(
        project_id=project_id,
        actor_user_id=current_user.sub,
    )
    return await use_case.execute(query)


@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_project_member(
    project_id: int,
    user_id: int,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[RemoveMemberUseCase, Depends(get_remove_member_use_case)],
    client_mutation_id: Annotated[str | None, Depends(get_client_mutation_id)],
):
    command = RemoveMemberCommand(
        project_id=project_id,
        user_id=user_id,
        requester_id=current_user.sub,
        client_mutation_id=client_mutation_id,
    )
    await use_case.execute(command)


@router.patch("/{project_id}/members/{user_id}", response_model=ProjectMemberRead)
async def update_member_role(
    project_id: int,
    user_id: int,
    member_update: ProjectMemberUpdate,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[UpdateMemberRoleUseCase, Depends(get_update_member_role_use_case)],
    client_mutation_id: Annotated[str | None, Depends(get_client_mutation_id)],
):
    command = UpdateMemberRoleCommand(
        project_id=project_id,
        user_id=user_id,
        role=member_update.role,
        requester_id=current_user.sub,
        client_mutation_id=client_mutation_id,
    )
    return await use_case.execute(command)
