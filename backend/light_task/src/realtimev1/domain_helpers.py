from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.boards.models import BoardColumn, Task
from src.boards.schemas import ColumnRead, TaskRead
from src.invitations.models import ProjectInvitation
from src.invitations.schemas import InvitationRead
from src.projects.models import Project, ProjectMember
from src.projects.schemas import ProjectMemberRead, ProjectRead
from src.tags.models import Tag
from src.tags.schemas import TagRead


async def get_project_member_user_ids(session: AsyncSession, project_id: int) -> list[int]:
    stmt = select(ProjectMember.user_id).where(ProjectMember.project_id == project_id)
    result = await session.execute(stmt)
    return [row[0] for row in result.all()]


async def get_project_updated_at(session: AsyncSession, project_id: int) -> datetime | None:
    stmt = select(Project.updated_at).where(Project.id == project_id)
    return await session.scalar(stmt)


def dump_project(project: Project, current_user_role: str | None = None) -> dict:
    data = ProjectRead.model_validate(project)
    if current_user_role is not None:
        data.current_user_role = current_user_role
    return data.model_dump(by_alias=True, mode="json")


def dump_project_member(member: ProjectMember) -> dict:
    data = ProjectMemberRead.model_validate(member)
    return data.model_dump(by_alias=True, mode="json")


def dump_tag(tag: Tag) -> dict:
    data = TagRead.model_validate(tag)
    return data.model_dump(by_alias=True, mode="json")


def dump_column(column: BoardColumn) -> dict:
    data = ColumnRead(
        id=column.id,
        project_id=column.project_id,
        name=column.name,
        position=column.position,
        tasks_limit=column.tasks_limit,
        tasks=[],
    )
    return data.model_dump(by_alias=True, mode="json")


def dump_task(task: Task) -> dict:
    data = TaskRead.model_validate(task)
    return data.model_dump(by_alias=True, mode="json")


def dump_invitation(invitation: ProjectInvitation) -> dict:
    data = InvitationRead.model_validate(invitation)
    return data.model_dump(by_alias=True, mode="json")
