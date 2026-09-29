from typing import Annotated

from fastapi import Depends

from src.assistant.cleanup import CheckpointCleanup
from src.assistant.dto import ProjectScope
from src.assistant.queries import AssistantProjectQueries
from src.assistant.runtime import AssistantRuntime
from src.assistant.tools import AssistantTools
from src.assistant.use_cases import (
    AssistantRunLifecycle,
    CreateConversationUseCase,
    DecideActionUseCase,
    DeleteConversationUseCase,
    GetConversationUseCase,
    ListConversationsUseCase,
    StartRunUseCase,
)
from src.boards.events import BoardsDomainEventDispatcher
from src.config import settings
from src.db.database import db_helper
from src.db.unit_of_work import UnitOfWork
from src.errors import ErrorCode
from src.projects.cache import ProjectReadCache, get_project_read_cache
from src.realtimev1.dependencies import get_event_publisher
from src.realtimev1.publisher import DomainEventPublisher
from src.shared.errors import ServiceUnavailableError
from src.tags.events import TagsDomainEventDispatcher


def require_enabled() -> None:
    if not settings.assistant.enabled:
        raise ServiceUnavailableError(ErrorCode.ASSISTANT_DISABLED)


def get_list_conversations_use_case() -> ListConversationsUseCase:
    return ListConversationsUseCase(db_helper.async_session_maker)


def get_create_conversation_use_case() -> CreateConversationUseCase:
    return CreateConversationUseCase(UnitOfWork)


def get_conversation_use_case() -> GetConversationUseCase:
    return GetConversationUseCase(db_helper.async_session_maker)


def get_checkpoint_cleanup() -> CheckpointCleanup:
    return CheckpointCleanup(UnitOfWork)


def get_delete_conversation_use_case() -> DeleteConversationUseCase:
    return DeleteConversationUseCase(UnitOfWork, get_checkpoint_cleanup())


def get_start_run_use_case() -> StartRunUseCase:
    return StartRunUseCase(UnitOfWork)


def get_decide_action_use_case() -> DecideActionUseCase:
    return DecideActionUseCase(UnitOfWork)


def make_assistant_tools(
    scope: ProjectScope, publisher: DomainEventPublisher, cache: ProjectReadCache
) -> AssistantTools:
    dispatcher = BoardsDomainEventDispatcher(db_helper.async_session_maker, publisher, cache)
    tag_dispatcher = TagsDomainEventDispatcher(db_helper.async_session_maker, publisher, cache)
    return AssistantTools(
        scope,
        AssistantProjectQueries(db_helper.async_session_maker, scope),
        lambda: UnitOfWork(event_dispatcher=dispatcher),
        lambda: UnitOfWork(event_dispatcher=tag_dispatcher),
    )


def get_assistant_runtime(
    publisher: Annotated[DomainEventPublisher, Depends(get_event_publisher)],
    cache: Annotated[ProjectReadCache, Depends(get_project_read_cache)],
) -> AssistantRuntime:
    return AssistantRuntime(
        lambda scope: make_assistant_tools(scope, publisher, cache),
        AssistantRunLifecycle(UnitOfWork),
    )
