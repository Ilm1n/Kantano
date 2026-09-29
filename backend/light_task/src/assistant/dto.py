from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID


@dataclass(frozen=True, kw_only=True)
class HistoryMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, kw_only=True)
class ProjectScope:
    project_id: int
    user_id: int


@dataclass(frozen=True, kw_only=True)
class ConversationScope(ProjectScope):
    conversation_id: UUID


@dataclass(frozen=True, kw_only=True)
class CreateConversationCommand(ProjectScope):
    title: str
    mode: str


@dataclass(frozen=True, kw_only=True)
class StartRunCommand(ConversationScope):
    content: str


@dataclass(frozen=True, kw_only=True)
class DecideActionCommand(ConversationScope):
    run_id: UUID
    action_id: str
    approve: bool


@dataclass(frozen=True, kw_only=True)
class StopRunCommand(ConversationScope):
    run_id: UUID


@dataclass(frozen=True, kw_only=True)
class RunExecution:
    run_id: UUID
    scope: ConversationScope
    history: list[HistoryMessage] = field(default_factory=list)
    approve: bool | None = None


@dataclass(frozen=True, kw_only=True)
class RunMetadata:
    provider: str | None = None
    model: str | None = None
    step_count: int = 0
    fallback_used: bool = False
