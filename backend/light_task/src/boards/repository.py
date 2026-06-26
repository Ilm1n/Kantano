from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.boards.constants import TaskPriority
from src.boards.models import BoardColumn, Task
from src.projects.models import Project, ProjectMember
from src.tags.models import Tag


class BoardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_project_columns(self, project_id: int) -> list[BoardColumn]:
        stmt = (
            select(BoardColumn)
            .where(BoardColumn.project_id == project_id)
            .order_by(BoardColumn.position.asc())
            .options(selectinload(BoardColumn.tasks).selectinload(Task.tags))
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_project_tasks(
        self,
        *,
        project_id: int,
        assignee_id: int | None = None,
        tag_ids: list[int] | None = None,
        search: str | None = None,
    ) -> list[Task]:
        stmt = (
            select(Task)
            .where(Task.project_id == project_id)
            .options(selectinload(Task.tags), selectinload(Task.assignee))
            .order_by(Task.updated_at.desc())
        )

        if assignee_id:
            stmt = stmt.where(Task.assignee_id == assignee_id)

        if search:
            stmt = stmt.where(
                or_(
                    Task.title.ilike(f"%{search}%"),
                    Task.description.ilike(f"%{search}%"),
                )
            )

        if tag_ids:
            stmt = stmt.join(Task.tags).where(Tag.id.in_(tag_ids)).distinct()

        return list((await self.session.execute(stmt)).scalars().all())

    async def get_column(self, column_id: int) -> BoardColumn | None:
        return await self.session.get(BoardColumn, column_id)

    async def get_column_in_project(
        self,
        *,
        project_id: int,
        column_id: int,
    ) -> BoardColumn | None:
        stmt = (
            select(BoardColumn)
            .where(
                BoardColumn.id == column_id,
                BoardColumn.project_id == project_id,
            )
            .options(selectinload(BoardColumn.tasks).selectinload(Task.tags))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_column_with_tasks(self, column_id: int) -> BoardColumn | None:
        stmt = (
            select(BoardColumn)
            .where(BoardColumn.id == column_id)
            .options(selectinload(BoardColumn.tasks).selectinload(Task.tags))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_max_column_position(self, project_id: int) -> float:
        stmt = select(func.max(BoardColumn.position)).where(BoardColumn.project_id == project_id)
        return await self.session.scalar(stmt) or 0.0

    def add_column(
        self,
        *,
        project_id: int,
        name: str,
        tasks_limit: int | None,
        position: float,
    ) -> BoardColumn:
        column = BoardColumn(
            name=name,
            tasks_limit=tasks_limit,
            project_id=project_id,
            position=position,
            tasks=[],
        )
        self.session.add(column)
        return column

    def save_column(self, column: BoardColumn) -> None:
        self.session.add(column)

    async def delete_column(self, column: BoardColumn) -> None:
        await self.session.delete(column)

    async def list_project_columns_by_ids(
        self,
        *,
        project_id: int,
        column_ids: Sequence[int],
    ) -> list[BoardColumn]:
        if not column_ids:
            return []

        stmt = select(BoardColumn).where(
            BoardColumn.project_id == project_id,
            BoardColumn.id.in_(column_ids),
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_tasks_in_column(self, column_id: int) -> int:
        stmt = select(func.count()).select_from(Task).where(Task.column_id == column_id)
        return await self.session.scalar(stmt) or 0

    async def get_max_task_position(self, column_id: int) -> float:
        stmt = select(func.max(Task.position)).where(Task.column_id == column_id)
        return await self.session.scalar(stmt) or 0.0

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

    async def project_member_exists(self, *, project_id: int, user_id: int) -> bool:
        stmt = (
            select(1)
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
            .limit(1)
        )
        return await self.session.scalar(stmt) is not None

    async def list_tags_by_ids(
        self,
        *,
        project_id: int,
        tag_ids: Sequence[int],
    ) -> list[Tag]:
        if not tag_ids:
            return []

        stmt = select(Tag).where(Tag.id.in_(tag_ids), Tag.project_id == project_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def add_task(
        self,
        *,
        title: str,
        description: str | None,
        priority: TaskPriority | None,
        deadline_at: datetime | None,
        project_id: int,
        column_id: int,
        assignee_id: int | None,
        author_id: int,
        position: float,
        tags: Sequence[Tag],
    ) -> Task:
        task = Task(
            title=title,
            description=description,
            priority=priority,
            deadline_at=deadline_at,
            project_id=project_id,
            column_id=column_id,
            assignee_id=assignee_id,
            author_id=author_id,
            position=position,
        )
        task.tags = list(tags)
        self.session.add(task)
        return task

    async def flush(self) -> None:
        await self.session.flush()

    async def touch_project(self, project_id: int) -> None:
        await self.session.execute(
            update(Project).where(Project.id == project_id).values(updated_at=func.now())
        )

    async def get_task_with_tags(self, task_id: int) -> Task | None:
        stmt = select(Task).where(Task.id == task_id).options(selectinload(Task.tags))
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_task_for_update(self, task_id: int) -> Task | None:
        stmt = select(Task).where(Task.id == task_id).options(selectinload(Task.tags))
        return (await self.session.execute(stmt)).scalar_one_or_none()

    def save_task(self, task: Task) -> None:
        self.session.add(task)

    async def delete_task(self, task: Task) -> None:
        await self.session.delete(task)

    async def get_first_task_position_for_update(self, column_id: int) -> float | None:
        stmt = (
            select(Task.position)
            .where(Task.column_id == column_id)
            .order_by(Task.position.asc())
            .limit(1)
            .with_for_update()
        )
        return await self.session.scalar(stmt)

    async def get_anchor_task_position_for_update(
        self,
        *,
        column_id: int,
        after_task_id: int,
    ) -> float | None:
        stmt = (
            select(Task.position)
            .where(Task.id == after_task_id, Task.column_id == column_id)
            .with_for_update()
        )
        return await self.session.scalar(stmt)

    async def get_next_task_position_for_update(
        self,
        *,
        column_id: int,
        anchor_position: float,
    ) -> float | None:
        stmt = (
            select(Task.position)
            .where(Task.column_id == column_id, Task.position > anchor_position)
            .order_by(Task.position.asc())
            .limit(1)
            .with_for_update()
        )
        return await self.session.scalar(stmt)

    async def list_column_tasks_for_update(self, column_id: int) -> list[Task]:
        stmt = (
            select(Task)
            .where(Task.column_id == column_id)
            .order_by(Task.position.asc())
            .with_for_update()
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_project_member_user_ids(self, project_id: int) -> list[int]:
        stmt = select(ProjectMember.user_id).where(ProjectMember.project_id == project_id)
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]

    async def get_project_updated_at(self, project_id: int):
        stmt = select(Project.updated_at).where(Project.id == project_id)
        return await self.session.scalar(stmt)
