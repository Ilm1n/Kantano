from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.invitations.models import ProjectInvitation
from src.projects.models import Project, ProjectMember


class InvitationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_project_member(
        self,
        *,
        project_id: int,
        user_id: int,
    ) -> ProjectMember | None:
        stmt = select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
        return await self.session.scalar(stmt)

    async def get_invitation(
        self,
        *,
        invitation_id: int,
        project_id: int,
    ) -> ProjectInvitation | None:
        stmt = select(ProjectInvitation).where(
            ProjectInvitation.id == invitation_id,
            ProjectInvitation.project_id == project_id,
        )
        return await self.session.scalar(stmt)

    async def list_project_invitations(
        self,
        project_id: int,
    ) -> list[ProjectInvitation]:
        stmt = (
            select(ProjectInvitation)
            .where(ProjectInvitation.project_id == project_id)
            .order_by(ProjectInvitation.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_invitation_by_token_for_update(
        self,
        token: str,
    ) -> ProjectInvitation | None:
        stmt = select(ProjectInvitation).where(ProjectInvitation.token == token).with_for_update()
        return await self.session.scalar(stmt)

    def add_invitation(self, invitation: ProjectInvitation) -> None:
        self.session.add(invitation)

    async def delete_invitation(self, invitation: ProjectInvitation) -> None:
        await self.session.delete(invitation)

    def save_invitation(self, invitation: ProjectInvitation) -> None:
        self.session.add(invitation)

    def add_member(self, member: ProjectMember) -> None:
        self.session.add(member)

    async def touch_project(self, project_id: int) -> None:
        await self.session.execute(
            update(Project).where(Project.id == project_id).values(updated_at=func.now())
        )

    async def flush(self) -> None:
        await self.session.flush()

    async def get_project_member_user_ids(self, project_id: int) -> list[int]:
        stmt = select(ProjectMember.user_id).where(ProjectMember.project_id == project_id)
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]

    async def get_project_updated_at(self, project_id: int):
        stmt = select(Project.updated_at).where(Project.id == project_id)
        return await self.session.scalar(stmt)
