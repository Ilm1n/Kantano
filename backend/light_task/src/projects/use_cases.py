from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.unit_of_work import UnitOfWork
from src.errors import ErrorCode
from src.logger import project_logger
from src.projects.constants import ProjectRole
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
from src.projects.events import (
    MemberRemoved,
    MemberRoleChanged,
    ProjectCreated,
    ProjectDeleted,
    ProjectUpdated,
)
from src.projects.models import ProjectMember
from src.projects.permissions import ProjectMemberPolicy
from src.projects.repository import ProjectRepository
from src.projects.schemas import ProjectRead
from src.shared.errors import AppError, DatabaseError, NotFoundError
from src.tags.constants import DEFAULT_PROJECT_TAGS
from src.tags.models import Tag


class ListUserProjectsUseCase:
    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def execute(self, query: ListUserProjectsQuery) -> list[ProjectRead]:
        try:
            async with self._session_factory() as session:
                repository = ProjectRepository(session)
                rows = await repository.list_user_projects(query.user_id)
                return [
                    ProjectRead(
                        id=project.id,
                        name=project.name,
                        description=project.description,
                        color=project.color,
                        owner_id=project.owner_id,
                        created_at=project.created_at,
                        updated_at=project.updated_at,
                        current_user_role=role,
                    )
                    for project, role in rows
                ]
        except AppError:
            raise
        except Exception as exc:
            project_logger.exception(
                "Failed to list projects for user %s",
                query.user_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class GetProjectDetailsUseCase:
    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def execute(self, query: GetProjectDetailsQuery) -> ProjectRead:
        try:
            async with self._session_factory() as session:
                repository = ProjectRepository(session)
                row = await repository.get_project_with_role(
                    project_id=query.project_id,
                    user_id=query.actor_user_id,
                )
                if row is None:
                    raise NotFoundError(ErrorCode.PROJECT_NOT_FOUND)

                project, role = row
                return ProjectRead(
                    id=project.id,
                    name=project.name,
                    description=project.description,
                    color=project.color,
                    owner_id=project.owner_id,
                    created_at=project.created_at,
                    updated_at=project.updated_at,
                    current_user_role=role,
                )
        except AppError:
            raise
        except Exception as exc:
            project_logger.exception(
                "Failed to read project %s for user %s",
                query.project_id,
                query.actor_user_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class ListProjectMembersUseCase:
    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        policy: ProjectMemberPolicy | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._policy = policy or ProjectMemberPolicy()

    async def execute(self, query: ListProjectMembersQuery) -> list[ProjectMember]:
        try:
            async with self._session_factory() as session:
                repository = ProjectRepository(session)
                requester_member = await repository.get_member(
                    project_id=query.project_id,
                    user_id=query.actor_user_id,
                )
                self._policy.ensure_project_member_can_read(requester_member=requester_member)
                return await repository.list_project_members(query.project_id)
        except AppError:
            raise
        except Exception as exc:
            project_logger.exception(
                "Failed to list members for project %s",
                query.project_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class CreateProjectUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
    ) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: CreateProjectCommand) -> ProjectRead:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = ProjectRepository(uow.session)
                project = repository.add_project(
                    name=command.name,
                    description=command.description,
                    color=command.color,
                    owner_id=command.owner_id,
                )
                await repository.flush()

                repository.add_member(
                    project_id=project.id,
                    user_id=command.owner_id,
                    role=ProjectRole.OWNER,
                )
                repository.add_tags(
                    [
                        Tag(
                            name=tag_data["name"],
                            color=tag_data["color"],
                            project_id=project.id,
                        )
                        for tag_data in DEFAULT_PROJECT_TAGS
                    ]
                )
                await repository.flush()
                await repository.refresh_project(project)

                uow.collect_event(
                    ProjectCreated(
                        user_id=command.owner_id,
                        actor_user_id=command.owner_id,
                        project_id=project.id,
                        client_mutation_id=command.client_mutation_id,
                    )
                )
                return ProjectRead(
                    id=project.id,
                    name=project.name,
                    description=project.description,
                    color=project.color,
                    owner_id=project.owner_id,
                    created_at=project.created_at,
                    updated_at=project.updated_at,
                    current_user_role=ProjectRole.OWNER,
                )
        except AppError:
            raise
        except Exception as exc:
            project_logger.exception(
                "Failed to create project for user %s",
                command.owner_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class UpdateProjectUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        policy: ProjectMemberPolicy | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._policy = policy or ProjectMemberPolicy()

    async def execute(self, command: UpdateProjectCommand) -> ProjectRead:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = ProjectRepository(uow.session)
                requester_member = await repository.get_member(
                    project_id=command.project_id,
                    user_id=command.actor_user_id,
                )
                self._policy.ensure_project_owner(requester_member=requester_member)

                project = await repository.get_project(command.project_id)
                if project is None:
                    raise NotFoundError(ErrorCode.PROJECT_NOT_FOUND)

                for key, value in command.changes.items():
                    setattr(project, key, value)
                project.updated_at = datetime.now(UTC)
                repository.save_project(project)
                await repository.flush()
                await repository.refresh_project(project)

                uow.collect_event(
                    ProjectUpdated(
                        actor_user_id=command.actor_user_id,
                        project_id=command.project_id,
                        client_mutation_id=command.client_mutation_id,
                    )
                )
                return ProjectRead(
                    id=project.id,
                    name=project.name,
                    description=project.description,
                    color=project.color,
                    owner_id=project.owner_id,
                    created_at=project.created_at,
                    updated_at=project.updated_at,
                    current_user_role=ProjectRole.OWNER,
                )
        except AppError:
            raise
        except Exception as exc:
            project_logger.exception(
                "Failed to update project %s",
                command.project_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class DeleteProjectUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        policy: ProjectMemberPolicy | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._policy = policy or ProjectMemberPolicy()

    async def execute(self, command: DeleteProjectCommand) -> None:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = ProjectRepository(uow.session)
                requester_member = await repository.get_member(
                    project_id=command.project_id,
                    user_id=command.actor_user_id,
                )
                self._policy.ensure_project_owner(requester_member=requester_member)

                project = await repository.get_project(command.project_id)
                if project is None:
                    raise NotFoundError(ErrorCode.PROJECT_NOT_FOUND)

                affected_user_ids = await repository.get_project_member_user_ids(command.project_id)
                await repository.delete_project(project)
                await repository.flush()
                uow.collect_event(
                    ProjectDeleted(
                        affected_user_ids=affected_user_ids,
                        actor_user_id=command.actor_user_id,
                        project_id=command.project_id,
                        client_mutation_id=command.client_mutation_id,
                    )
                )
        except AppError:
            raise
        except Exception as exc:
            project_logger.exception(
                "Failed to delete project %s",
                command.project_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class RemoveMemberUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        policy: ProjectMemberPolicy | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._policy = policy or ProjectMemberPolicy()

    async def execute(self, command: RemoveMemberCommand) -> None:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = ProjectRepository(uow.session)
                target_member = await repository.get_member(
                    project_id=command.project_id,
                    user_id=command.user_id,
                )
                if target_member is None:
                    raise NotFoundError(ErrorCode.MEMBER_NOT_FOUND)

                requester_member = await repository.get_member(
                    project_id=command.project_id,
                    user_id=command.requester_id,
                )
                self._policy.ensure_can_remove_member(
                    requester_member=requester_member,
                    target_member=target_member,
                )

                await repository.delete_member(target_member)
                await repository.touch_project(command.project_id)
                await repository.flush()
                remaining_user_ids = await repository.get_project_member_user_ids(
                    command.project_id
                )
                uow.collect_event(
                    MemberRemoved(
                        user_id=command.user_id,
                        remaining_user_ids=remaining_user_ids,
                        actor_user_id=command.requester_id,
                        project_id=command.project_id,
                        client_mutation_id=command.client_mutation_id,
                    )
                )
        except AppError:
            raise
        except Exception as exc:
            project_logger.exception(
                "Failed to remove member %s from project %s",
                command.user_id,
                command.project_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class UpdateMemberRoleUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        policy: ProjectMemberPolicy | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._policy = policy or ProjectMemberPolicy()

    async def execute(self, command: UpdateMemberRoleCommand) -> ProjectMember:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = ProjectRepository(uow.session)
                target_member = await repository.get_member(
                    project_id=command.project_id,
                    user_id=command.user_id,
                    with_user=True,
                )
                if target_member is None:
                    raise NotFoundError(ErrorCode.MEMBER_NOT_FOUND)

                requester_member = await repository.get_member(
                    project_id=command.project_id,
                    user_id=command.requester_id,
                )
                self._policy.ensure_can_update_member_role(
                    requester_member=requester_member,
                    target_member=target_member,
                )

                previous_role = target_member.role
                target_member.role = command.role
                repository.save_member(target_member)
                await repository.touch_project(command.project_id)
                await repository.flush()
                affected_user_ids = await repository.get_project_member_user_ids(command.project_id)
                uow.collect_event(
                    MemberRoleChanged(
                        user_id=command.user_id,
                        role=target_member.role,
                        previous_role=previous_role,
                        affected_user_ids=affected_user_ids,
                        actor_user_id=command.requester_id,
                        project_id=command.project_id,
                        client_mutation_id=command.client_mutation_id,
                    )
                )
                return target_member
        except AppError:
            raise
        except Exception as exc:
            project_logger.exception(
                "Failed to update member %s role in project %s",
                command.user_id,
                command.project_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc
