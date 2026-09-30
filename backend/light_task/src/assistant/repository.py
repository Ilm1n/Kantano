from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.assistant.contracts import ACTIVE_RUN_STATUSES, EXECUTING_RUN_STATUSES
from src.assistant.models import (
    AssistantCheckpointCleanup,
    AssistantConversation,
    AssistantMessage,
    AssistantRun,
)
from src.boards.models import BoardColumn, Task
from src.projects.models import Project, ProjectMember
from src.tags.models import Tag
from src.users.models import User


class AssistantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def is_member(self, project_id: int, user_id: int) -> bool:
        statement = select(ProjectMember.id).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user_id
        )
        return await self.session.scalar(statement) is not None

    async def list_conversations(
        self, project_id: int, user_id: int
    ) -> list[AssistantConversation]:
        statement = (
            select(AssistantConversation)
            .where(
                AssistantConversation.project_id == project_id,
                AssistantConversation.user_id == user_id,
            )
            .order_by(AssistantConversation.updated_at.desc())
        )
        return list((await self.session.scalars(statement)).all())

    async def get_conversation(
        self, project_id: int, user_id: int, conversation_id: UUID, *, for_update: bool = False
    ) -> AssistantConversation | None:
        statement = select(AssistantConversation).where(
            AssistantConversation.id == conversation_id,
            AssistantConversation.project_id == project_id,
            AssistantConversation.user_id == user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def list_messages(self, conversation_id: UUID) -> list[AssistantMessage]:
        statement = (
            select(AssistantMessage)
            .where(AssistantMessage.conversation_id == conversation_id)
            .order_by(AssistantMessage.created_at, AssistantMessage.id)
        )
        return list((await self.session.scalars(statement)).all())

    async def list_runs(self, conversation_id: UUID) -> list[AssistantRun]:
        statement = select(AssistantRun).where(AssistantRun.conversation_id == conversation_id)
        return list((await self.session.scalars(statement)).all())

    async def latest_run(self, conversation_id: UUID) -> AssistantRun | None:
        statement = (
            select(AssistantRun)
            .where(AssistantRun.conversation_id == conversation_id)
            .order_by(AssistantRun.created_at.desc(), AssistantRun.id.desc())
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def claim_pending(self, run_id: UUID, action_id: str, next_status: str) -> bool:
        statement = (
            update(AssistantRun)
            .where(
                AssistantRun.id == run_id,
                AssistantRun.status == "pending",
                AssistantRun.stop_requested.is_(False),
                func.coalesce(
                    AssistantRun.proposed_action["action_id"].as_string(),
                    AssistantRun.proposed_action["tool_call_id"].as_string(),
                )
                == action_id,
            )
            .values(status=next_status, updated_at=datetime.now(UTC))
            .returning(AssistantRun.id)
        )
        return await self.session.scalar(statement) is not None

    async def touch_conversation(self, conversation: AssistantConversation) -> None:
        conversation.updated_at = datetime.now(UTC)
        self.session.add(conversation)

    async def lock_project(self, project_id: int) -> bool:
        statement = select(Project.id).where(Project.id == project_id).with_for_update(read=True)
        return await self.session.scalar(statement) is not None

    async def active_run(self, conversation_id: UUID) -> AssistantRun | None:
        statement = (
            select(AssistantRun)
            .where(
                AssistantRun.conversation_id == conversation_id,
                AssistantRun.status.in_(ACTIVE_RUN_STATUSES),
            )
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def get_run(self, run_id: UUID, *, for_update: bool = False) -> AssistantRun | None:
        return await self.session.get(AssistantRun, run_id, with_for_update=for_update)

    async def stop_requested(self, run_id: UUID) -> bool:
        return bool(
            await self.session.scalar(
                select(AssistantRun.stop_requested).where(AssistantRun.id == run_id)
            )
        )

    def add_conversation(self, conversation: AssistantConversation) -> None:
        self.session.add(conversation)

    def add_message(self, message: AssistantMessage) -> None:
        self.session.add(message)

    def add_run(self, run: AssistantRun) -> None:
        self.session.add(run)

    async def get_message(self, message_id: UUID) -> AssistantMessage | None:
        return await self.session.get(AssistantMessage, message_id)

    async def delete_conversation(self, conversation: AssistantConversation) -> None:
        await self.session.delete(conversation)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, conversation: AssistantConversation) -> None:
        await self.session.refresh(conversation)

    async def update_run(self, run_id: UUID, **values: Any) -> None:
        await self.session.execute(
            update(AssistantRun).where(AssistantRun.id == run_id).values(**values)
        )

    async def interrupt_run(self, run_id: UUID | None = None) -> list[AssistantRun]:
        statement = update(AssistantRun).where(AssistantRun.status.in_(EXECUTING_RUN_STATUSES))
        if run_id is not None:
            statement = statement.where(AssistantRun.id == run_id)
        result = await self.session.scalars(
            statement.values(
                status=case((AssistantRun.status == "executing", "unknown"), else_="interrupted")
            ).returning(AssistantRun)
        )
        return list(result.all())

    async def project_runs(self, project_id: int) -> list[AssistantRun]:
        statement = (
            select(AssistantRun)
            .join(AssistantConversation)
            .where(AssistantConversation.project_id == project_id)
        )
        return list((await self.session.scalars(statement)).all())

    def queue_checkpoint_cleanup(self, run_ids: list[UUID]) -> None:
        self.session.add_all([AssistantCheckpointCleanup(thread_id=run_id) for run_id in run_ids])

    async def next_checkpoint_cleanup(self) -> AssistantCheckpointCleanup | None:
        statement = (
            select(AssistantCheckpointCleanup)
            .order_by(AssistantCheckpointCleanup.created_at, AssistantCheckpointCleanup.thread_id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def remove_checkpoint_cleanup(self, cleanup: AssistantCheckpointCleanup) -> None:
        await self.session.delete(cleanup)

    async def get_project(self, project_id: int) -> Project | None:
        return await self.session.get(Project, project_id)

    async def project_columns(self, project_id: int) -> list[BoardColumn]:
        statement = (
            select(BoardColumn)
            .where(BoardColumn.project_id == project_id)
            .order_by(BoardColumn.position, BoardColumn.id)
        )
        return list((await self.session.scalars(statement)).all())

    async def task_counts(self, project_id: int) -> dict[int, int]:
        statement = (
            select(Task.column_id, func.count(Task.id))
            .where(Task.project_id == project_id)
            .group_by(Task.column_id)
        )
        return dict((await self.session.execute(statement)).tuples().all())

    async def project_users(self, project_id: int) -> list[User]:
        statement = (
            select(User)
            .join(ProjectMember, ProjectMember.user_id == User.id)
            .where(ProjectMember.project_id == project_id)
        )
        return list((await self.session.scalars(statement)).all())

    async def project_tags(self, project_id: int) -> list[Tag]:
        return list(
            (await self.session.scalars(select(Tag).where(Tag.project_id == project_id))).all()
        )

    async def entity_label(
        self, kind: Literal["task", "column", "tag"], project_id: int, entity_id: int
    ) -> str | None:
        model, title = {
            "task": (Task, Task.title),
            "column": (BoardColumn, BoardColumn.name),
            "tag": (Tag, Tag.name),
        }[kind]
        return await self.session.scalar(
            select(title).where(model.id == entity_id, model.project_id == project_id)
        )

    async def task_titles(self, project_id: int, task_ids: list[int]) -> dict[int, str]:
        statement = select(Task.id, Task.title).where(
            Task.project_id == project_id, Task.id.in_(task_ids)
        )
        return dict((await self.session.execute(statement)).tuples().all())
