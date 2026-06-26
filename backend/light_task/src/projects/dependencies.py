from typing import Annotated

from fastapi import Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.schemas import UserPayload
from src.db.database import db_helper
from src.projects.constants import ProjectRole
from src.projects.models import Project
from src.projects.permissions import ProjectMemberPolicy
from src.projects.repository import ProjectRepository


class ProjectAccessChecker:
    def __init__(self, allowed_roles: list[ProjectRole]):
        self.allowed_roles = allowed_roles
        self.policy = ProjectMemberPolicy()

    async def __call__(
        self,
        project_id: Annotated[int, Path()],
        user: Annotated[UserPayload, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(db_helper.get_async_session)],
    ) -> Project:
        repository = ProjectRepository(session)
        member = await repository.get_member(
            project_id=project_id,
            user_id=user.sub,
            with_project=True,
        )
        self.policy.ensure_role_allowed(
            requester_member=member,
            allowed_roles=self.allowed_roles,
        )
        return member.project


class ProjectPermissionChecker:
    def __init__(self, allowed_roles: list[ProjectRole]):
        self.allowed_roles = allowed_roles
        self.policy = ProjectMemberPolicy()

    async def __call__(
        self,
        project_id: Annotated[int, Path()],
        user: Annotated[UserPayload, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(db_helper.get_async_session)],
    ) -> None:
        repository = ProjectRepository(session)
        member = await repository.get_member(
            project_id=project_id,
            user_id=user.sub,
        )
        self.policy.ensure_role_allowed(
            requester_member=member,
            allowed_roles=self.allowed_roles,
        )


require_project_owner = ProjectAccessChecker([ProjectRole.OWNER])
require_project_manager = ProjectAccessChecker([ProjectRole.OWNER, ProjectRole.MANAGER])
require_project_member = ProjectAccessChecker(
    [ProjectRole.OWNER, ProjectRole.MANAGER, ProjectRole.MEMBER]
)

check_project_owner = ProjectPermissionChecker([ProjectRole.OWNER])
check_project_manager = ProjectPermissionChecker([ProjectRole.OWNER, ProjectRole.MANAGER])
check_project_member = ProjectPermissionChecker(
    [ProjectRole.OWNER, ProjectRole.MANAGER, ProjectRole.MEMBER]
)
