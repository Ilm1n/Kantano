from datetime import datetime
from uuid import UUID

from pydantic import Field

from src.schemas import BaseSchema


class ConversationCreate(BaseSchema):
    title: str = Field(default="Новый чат", min_length=1, max_length=100)


class ConversationRead(BaseSchema):
    id: UUID
    project_id: int
    title: str
    mode: str
    created_at: datetime
    updated_at: datetime


class MessageRead(BaseSchema):
    id: UUID
    role: str
    content: str
    references: list[dict]
    created_at: datetime


class RunRead(BaseSchema):
    id: UUID
    status: str
    provider: str | None
    model: str | None
    step_count: int
    fallback_used: bool
    proposed_action: dict | None
    result: dict | None
    created_at: datetime
    updated_at: datetime


class ChatDetail(BaseSchema):
    conversation: ConversationRead
    messages: list[MessageRead]
    latest_run: RunRead | None


class MessageCreate(BaseSchema):
    content: str = Field(min_length=1, max_length=8000)


class ActionDecision(BaseSchema):
    approve: bool
