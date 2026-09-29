from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from src.assistant.contracts import ActionKind, ActionName, ActionStatus, RunStatus, WriteToolName
from src.schemas import BaseSchema


class ConversationCreate(BaseSchema):
    title: str = Field(default="Новый чат", min_length=1, max_length=100)


class ConversationRead(BaseSchema):
    id: UUID
    project_id: int
    title: str
    mode: Literal["local", "cloud"]
    created_at: datetime
    updated_at: datetime


class TaskReference(BaseSchema):
    type: Literal["task"] = "task"
    id: int
    title: str | None = None


class MessageRead(BaseSchema):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    references: list[TaskReference]
    created_at: datetime


class ActionStep(BaseModel):
    id: str
    tool: WriteToolName
    args: dict[str, Any]
    display: dict[str, Any] = Field(default_factory=dict)


class ActionDisplay(BaseModel):
    steps: list[ActionStep] | None = None
    task_id: str | None = None
    column_id: str | None = None
    new_column_id: str | None = None
    before_column_id: str | None = None
    tag_id: str | None = None
    assignee_id: str | None = None
    tag_ids: list[str] | None = None


class ActionCall(BaseModel):
    id: str
    start: int
    end: int


class ProposedAction(BaseModel):
    name: ActionName
    args: dict[str, Any]
    display: ActionDisplay | None = None
    action_id: str | None = None
    tool_call_id: str
    calls: list[ActionCall] | None = None


class ActionOutcome(BaseModel):
    status: ActionStatus = "completed"
    tool: WriteToolName | None = None
    action_id: str | None = None
    step_id: str | None = None
    kind: ActionKind | None = None
    task_id: int | None = None
    column_id: int | None = None
    tag_id: int | None = None
    title: str | None = None
    name: str | None = None
    error: str | None = None
    error_code: str | None = None


class RunResult(BaseModel):
    actions: list[ActionOutcome] = Field(default_factory=list)
    error: str | None = None


class RunRead(BaseSchema):
    id: UUID
    status: RunStatus
    provider: str | None
    model: str | None
    step_count: int
    fallback_used: bool
    proposed_action: ProposedAction | None
    result: RunResult | None
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
    action_id: str = Field(min_length=1, max_length=128)
