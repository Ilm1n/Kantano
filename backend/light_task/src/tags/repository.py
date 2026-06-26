from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.projects.models import Project, ProjectMember
from src.tags.models import Tag


class TagRepository:
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

    async def get_tag(self, tag_id: int) -> Tag | None:
        return await self.session.get(Tag, tag_id)

    async def list_project_tags(self, project_id: int) -> list[Tag]:
        stmt = select(Tag).where(Tag.project_id == project_id).order_by(Tag.name)
        return list((await self.session.execute(stmt)).scalars().all())

    async def find_tag_by_name(
        self,
        *,
        project_id: int,
        name: str,
    ) -> Tag | None:
        stmt = select(Tag).where(Tag.project_id == project_id, Tag.name == name)
        return await self.session.scalar(stmt)

    def add_tag(self, tag: Tag) -> None:
        self.session.add(tag)

    def save_tag(self, tag: Tag) -> None:
        self.session.add(tag)

    async def delete_tag(self, tag: Tag) -> None:
        await self.session.delete(tag)

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
