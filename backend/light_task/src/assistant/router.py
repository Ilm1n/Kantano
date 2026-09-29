from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from src.assistant.dependencies import (
    get_assistant_runtime,
    get_conversation_use_case,
    get_create_conversation_use_case,
    get_decide_action_use_case,
    get_delete_conversation_use_case,
    get_list_conversations_use_case,
    get_start_run_use_case,
    require_enabled,
)
from src.assistant.dto import (
    ConversationScope,
    CreateConversationCommand,
    DecideActionCommand,
    ProjectScope,
    StartRunCommand,
)
from src.assistant.responses import AssistantStreamingResponse, encode_events
from src.assistant.runtime import AssistantRuntime
from src.assistant.schemas import (
    ActionDecision,
    ChatDetail,
    ConversationCreate,
    ConversationRead,
    MessageCreate,
)
from src.assistant.use_cases import (
    CreateConversationUseCase,
    DecideActionUseCase,
    DeleteConversationUseCase,
    GetConversationUseCase,
    ListConversationsUseCase,
    StartRunUseCase,
)
from src.auth.dependencies import get_current_user
from src.auth.schemas import UserPayload
from src.config import settings

router = APIRouter(
    prefix="/projects/{project_id}/assistant",
    tags=["Assistant"],
    dependencies=[Depends(require_enabled)],
)
User = Annotated[UserPayload, Depends(get_current_user)]
Runtime = Annotated[AssistantRuntime, Depends(get_assistant_runtime)]
SSE_RESPONSES: dict[int | str, dict[str, Any]] = {200: {"content": {"text/event-stream": {}}}}


@router.get("/conversations", response_model=list[ConversationRead])
async def list_conversations(
    project_id: int,
    user: User,
    use_case: Annotated[ListConversationsUseCase, Depends(get_list_conversations_use_case)],
) -> list[ConversationRead]:
    return await use_case.execute(ProjectScope(project_id=project_id, user_id=user.sub))


@router.post("/conversations", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    project_id: int,
    body: ConversationCreate,
    user: User,
    use_case: Annotated[CreateConversationUseCase, Depends(get_create_conversation_use_case)],
) -> ConversationRead:
    return await use_case.execute(
        CreateConversationCommand(
            project_id=project_id,
            user_id=user.sub,
            title=body.title,
            mode=settings.assistant.mode,
        )
    )


@router.get("/conversations/{conversation_id}", response_model=ChatDetail)
async def get_conversation(
    project_id: int,
    conversation_id: UUID,
    user: User,
    use_case: Annotated[GetConversationUseCase, Depends(get_conversation_use_case)],
) -> ChatDetail:
    return await use_case.execute(
        ConversationScope(
            project_id=project_id,
            user_id=user.sub,
            conversation_id=conversation_id,
        )
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    project_id: int,
    conversation_id: UUID,
    user: User,
    use_case: Annotated[DeleteConversationUseCase, Depends(get_delete_conversation_use_case)],
) -> None:
    await use_case.execute(
        ConversationScope(
            project_id=project_id,
            user_id=user.sub,
            conversation_id=conversation_id,
        )
    )


@router.post(
    "/conversations/{conversation_id}/runs",
    response_class=StreamingResponse,
    responses=SSE_RESPONSES,
)
async def start_run(
    project_id: int,
    conversation_id: UUID,
    body: MessageCreate,
    user: User,
    runtime: Runtime,
    use_case: Annotated[StartRunUseCase, Depends(get_start_run_use_case)],
) -> StreamingResponse:
    execution = await use_case.execute(
        StartRunCommand(
            project_id=project_id,
            user_id=user.sub,
            conversation_id=conversation_id,
            content=body.content,
        )
    )
    return AssistantStreamingResponse(
        encode_events(runtime.stream(execution)), execution.run_id, runtime.interrupt
    )


@router.post(
    "/conversations/{conversation_id}/runs/{run_id}/decision",
    response_class=StreamingResponse,
    responses=SSE_RESPONSES,
)
async def decide_action(
    project_id: int,
    conversation_id: UUID,
    run_id: UUID,
    body: ActionDecision,
    user: User,
    runtime: Runtime,
    use_case: Annotated[DecideActionUseCase, Depends(get_decide_action_use_case)],
) -> StreamingResponse:
    execution = await use_case.execute(
        DecideActionCommand(
            project_id=project_id,
            user_id=user.sub,
            conversation_id=conversation_id,
            run_id=run_id,
            action_id=body.action_id,
            approve=body.approve,
        )
    )
    return AssistantStreamingResponse(
        encode_events(runtime.stream(execution)), execution.run_id, runtime.interrupt
    )
