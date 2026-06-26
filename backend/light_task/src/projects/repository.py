from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.projects.constants import ProjectRole
from src.projects.models import Project, ProjectMember
from src.tags.models import Tag


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_project(self, project_id: int) -> Project | None:
        return await self.session.get(Project, project_id)

    async def list_user_projects(self, user_id: int) -> list[tuple[Project, ProjectRole]]:
        stmt = (
            select(Project, ProjectMember.role)
            .join(ProjectMember, Project.id == ProjectMember.project_id)
            .where(ProjectMember.user_id == user_id)
            .order_by(Project.updated_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.all())

    async def get_project_with_role(
        self,
        *,
        project_id: int,
        user_id: int,
    ) -> tuple[Project, ProjectRole] | None:
        stmt = (
            select(Project, ProjectMember.role)
            .join(ProjectMember, Project.id == ProjectMember.project_id)
            .where(
                Project.id == project_id,
                ProjectMember.user_id == user_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.first()

    async def list_project_members(self, project_id: int) -> list[ProjectMember]:
        stmt = (
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id)
            .options(selectinload(ProjectMember.user))
            .order_by(ProjectMember.joined_at)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    def add_project(
        self,
        *,
        name: str,
        description: str | None,
        color: str,
        owner_id: int,
    ) -> Project:
        project = Project(
            name=name,
            description=description,
            color=color,
            owner_id=owner_id,
        )
        self.session.add(project)
        return project

    def save_project(self, project: Project) -> None:
        self.session.add(project)

    async def delete_project(self, project: Project) -> None:
        await self.session.delete(project)

    async def refresh_project(self, project: Project) -> None:
        await self.session.refresh(project)

    async def get_member(
        self,
        *,
        project_id: int,
        user_id: int,
        with_user: bool = False,
        with_project: bool = False,
    ) -> ProjectMember | None:
        stmt = select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
        if with_user:
            stmt = stmt.options(selectinload(ProjectMember.user))
        if with_project:
            stmt = stmt.options(selectinload(ProjectMember.project))
        return await self.session.scalar(stmt)

    def add_member(
        self,
        *,
        project_id: int,
        user_id: int,
        role: ProjectRole,
    ) -> ProjectMember:
        member = ProjectMember(project_id=project_id, user_id=user_id, role=role)
        self.session.add(member)
        return member

    def save_member(self, member: ProjectMember) -> None:
        self.session.add(member)

    async def delete_member(self, member: ProjectMember) -> None:
        await self.session.delete(member)

    def add_tags(self, tags: list[Tag]) -> None:
        self.session.add_all(tags)

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
