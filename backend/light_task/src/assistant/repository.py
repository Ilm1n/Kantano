from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.assistant.models import AssistantConversation, AssistantMessage, AssistantRun
from src.projects.models import ProjectMember


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
        self, project_id: int, user_id: int, conversation_id: UUID
    ) -> AssistantConversation | None:
        statement = select(AssistantConversation).where(
            AssistantConversation.id == conversation_id,
            AssistantConversation.project_id == project_id,
            AssistantConversation.user_id == user_id,
        )
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
