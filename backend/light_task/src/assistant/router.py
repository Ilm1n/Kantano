# ruff: noqa: RUF001
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from time import perf_counter
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.types import Command
from sqlalchemy import update

from src.assistant.checkpoints import open_checkpointer
from src.assistant.graph import build_graph
from src.assistant.models import AssistantConversation, AssistantMessage, AssistantRun
from src.assistant.repository import AssistantRepository
from src.assistant.schemas import (
    ActionDecision,
    ChatDetail,
    ConversationCreate,
    ConversationRead,
    MessageCreate,
    MessageRead,
    RunRead,
)
from src.assistant.tools import AssistantTools
from src.auth.dependencies import get_current_user
from src.auth.schemas import UserPayload
from src.config import settings
from src.db.database import db_helper
from src.db.unit_of_work import UnitOfWork
from src.projects.cache import get_project_read_cache
from src.realtimev1.dependencies import get_event_publisher

router = APIRouter(prefix="/projects/{project_id}/assistant", tags=["Assistant"])
logger = logging.getLogger(__name__)


def require_enabled() -> None:
    if not settings.assistant.enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Assistant is disabled")


async def authorized_chat(
    project_id: int, user_id: int, conversation_id: UUID
) -> AssistantConversation:
    async with db_helper.async_session_maker() as session:
        repository = AssistantRepository(session)
        if not await repository.is_member(project_id, user_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
        conversation = await repository.get_conversation(project_id, user_id, conversation_id)
        if conversation is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat not found")
        return conversation


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def public_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


@router.get(
    "/conversations", response_model=list[ConversationRead], dependencies=[Depends(require_enabled)]
)
async def list_conversations(
    project_id: int, user: Annotated[UserPayload, Depends(get_current_user)]
) -> list[AssistantConversation]:
    async with db_helper.async_session_maker() as session:
        repository = AssistantRepository(session)
        if not await repository.is_member(project_id, user.sub):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
        return await repository.list_conversations(project_id, user.sub)


@router.post(
    "/conversations",
    response_model=ConversationRead,
    status_code=201,
    dependencies=[Depends(require_enabled)],
)
async def create_conversation(
    project_id: int,
    body: ConversationCreate,
    user: Annotated[UserPayload, Depends(get_current_user)],
) -> AssistantConversation:
    async with UnitOfWork() as uow:
        session = uow.session
        if session is None:
            raise RuntimeError("UnitOfWork has not been entered")
        repository = AssistantRepository(session)
        if not await repository.is_member(project_id, user.sub):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
        conversation = AssistantConversation(
            project_id=project_id,
            user_id=user.sub,
            title=body.title,
            mode=settings.assistant.mode,
        )
        session.add(conversation)
        await session.flush()
        await session.refresh(conversation)
    return conversation


@router.get(
    "/conversations/{conversation_id}",
    response_model=ChatDetail,
    dependencies=[Depends(require_enabled)],
)
async def get_conversation(
    project_id: int,
    conversation_id: UUID,
    user: Annotated[UserPayload, Depends(get_current_user)],
) -> ChatDetail:
    conversation = await authorized_chat(project_id, user.sub, conversation_id)
    async with db_helper.async_session_maker() as session:
        repository = AssistantRepository(session)
        messages = await repository.list_messages(conversation_id)
        latest_run = await repository.latest_run(conversation_id)
        return ChatDetail(
            conversation=ConversationRead.model_validate(conversation),
            messages=[MessageRead.model_validate(message) for message in messages],
            latest_run=RunRead.model_validate(latest_run) if latest_run else None,
        )


@router.delete(
    "/conversations/{conversation_id}",
    status_code=204,
    dependencies=[Depends(require_enabled)],
)
async def delete_conversation(
    project_id: int,
    conversation_id: UUID,
    user: Annotated[UserPayload, Depends(get_current_user)],
) -> None:
    await authorized_chat(project_id, user.sub, conversation_id)
    async with UnitOfWork() as uow:
        session = uow.session
        if session is None:
            raise RuntimeError("UnitOfWork has not been entered")
        repository = AssistantRepository(session)
        conversation = await repository.get_conversation(project_id, user.sub, conversation_id)
        if conversation is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat not found")
        runs = await repository.list_runs(conversation_id)
        if any(run.status in {"running", "executing"} for run in runs):
            raise HTTPException(status.HTTP_409_CONFLICT, "Chat has an active run")
        async with open_checkpointer() as saver:
            for run in runs:
                await saver.adelete_thread(str(run.id))
        await session.delete(conversation)


async def persist_run_state(run_id: UUID, **values: Any) -> None:
    async with UnitOfWork() as uow:
        session = uow.session
        if session is None:
            raise RuntimeError("UnitOfWork has not been entered")
        await session.execute(
            update(AssistantRun).where(AssistantRun.id == run_id).values(**values)
        )


async def stream_graph(
    *,
    run_id: UUID,
    conversation_id: UUID,
    project_id: int,
    user_id: int,
    request: Request,
    input_value: Any,
    approved: bool | None = None,
) -> AsyncIterator[str]:
    start = perf_counter()
    publisher = get_event_publisher(request)
    cache = get_project_read_cache(request)
    tools = AssistantTools(project_id, user_id, publisher, cache)
    config = {"configurable": {"thread_id": str(run_id)}}
    yield sse("run", {"run_id": str(run_id), "status": "running"})
    try:
        async with open_checkpointer() as saver:
            graph = build_graph(saver, tools)
            streamed_node_text = ""
            async for mode, event in graph.astream(
                input_value, config, stream_mode=["messages", "updates"]
            ):
                if mode == "messages":
                    chunk, metadata = event
                    if metadata.get("langgraph_node") == "agent" and isinstance(
                        chunk, AIMessageChunk
                    ):
                        token = public_text(chunk.content)
                        if token:
                            streamed_node_text += token
                            yield sse("delta", {"text": token})
                elif "agent" in event:
                    agent_update = event["agent"]
                    answer = agent_update["messages"][-1]
                    if isinstance(answer, AIMessage) and not answer.tool_calls:
                        content = public_text(answer.content)
                        if agent_update.get("last_fallback_used"):
                            yield sse("reset", {})
                            yield sse("delta", {"text": content})
                        elif not streamed_node_text and content:
                            yield sse("delta", {"text": content})
                    streamed_node_text = ""
            snapshot = await graph.aget_state(config)
            state = snapshot.values
            metadata = {
                "provider": state.get("provider"),
                "model": state.get("model"),
                "step_count": state.get("step_count", 0),
                "fallback_used": state.get("fallback_used", False),
            }
            pending = any(task.interrupts for task in snapshot.tasks)
            if pending:
                action = state.get("proposed_action")
                await persist_run_state(
                    run_id,
                    status="pending",
                    proposed_action=action,
                    **metadata,
                )
                yield sse("approval_required", {"action": action, **metadata})
                final_status = "pending"
            else:
                messages = state.get("messages", [])
                answer = messages[-1] if messages else None
                content = public_text(answer.content) if isinstance(answer, AIMessage) else ""
                final_status = "rejected" if approved is False else "completed"
                async with UnitOfWork() as uow:
                    session = uow.session
                    if session is None:
                        raise RuntimeError("UnitOfWork has not been entered")
                    session.add(
                        AssistantMessage(
                            conversation_id=conversation_id,
                            role="assistant",
                            content=content,
                            references=state.get("references", []),
                        )
                    )
                    await session.execute(
                        update(AssistantRun)
                        .where(AssistantRun.id == run_id)
                        .values(
                            status=final_status,
                            proposed_action=None,
                            result=state.get("tool_result"),
                            **metadata,
                        )
                    )
                yield sse("done", {"status": final_status, "message": content, **metadata})
            logger.info(
                "assistant_run run_id=%s conversation_id=%s provider=%s model=%s "
                "steps=%s llm_duration_ms=%s fallback=%s tool_result=%s status=%s total_ms=%s",
                run_id,
                conversation_id,
                state.get("provider"),
                state.get("model"),
                state.get("step_count", 0),
                state.get("llm_duration_ms", 0),
                state.get("fallback_used", False),
                (state.get("tool_result") or {}).get("kind", "none"),
                final_status,
                int((perf_counter() - start) * 1000),
            )
    except asyncio.CancelledError:
        await persist_run_state(run_id, status="interrupted")
        raise
    except Exception as exc:
        await persist_run_state(
            run_id,
            status="unknown" if approved else "failed",
            result={"error": "Run stopped; review before retrying any action"},
        )
        logger.error(
            "assistant_run_failed run_id=%s conversation_id=%s error_type=%s",
            run_id,
            conversation_id,
            type(exc).__name__,
        )
        yield sse("error", {"message": "Не удалось выполнить запрос", "run_id": str(run_id)})


def stream_response(stream: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/conversations/{conversation_id}/runs", dependencies=[Depends(require_enabled)])
async def start_run(
    project_id: int,
    conversation_id: UUID,
    body: MessageCreate,
    request: Request,
    user: Annotated[UserPayload, Depends(get_current_user)],
) -> StreamingResponse:
    await authorized_chat(project_id, user.sub, conversation_id)
    async with UnitOfWork() as uow:
        session = uow.session
        if session is None:
            raise RuntimeError("UnitOfWork has not been entered")
        repository = AssistantRepository(session)
        previous = await repository.latest_run(conversation_id)
        if previous and previous.status in {"running", "pending", "executing"}:
            raise HTTPException(status.HTTP_409_CONFLICT, "Resolve the current run first")
        history = await repository.list_messages(conversation_id)
        session.add(
            AssistantMessage(
                conversation_id=conversation_id,
                role="user",
                content=body.content,
                references=[],
            )
        )
        run = AssistantRun(conversation_id=conversation_id, status="running")
        session.add(run)
        conversation = await repository.get_conversation(project_id, user.sub, conversation_id)
        if conversation is not None:
            if not history and conversation.title == "Новый чат":
                conversation.title = body.content[:80]
            await repository.touch_conversation(conversation)
        await session.flush()
        run_id = run.id
    graph_history = [
        HumanMessage(content=message.content)
        if message.role == "user"
        else AIMessage(content=message.content)
        for message in history[-20:]
    ]
    graph_history.append(HumanMessage(content=body.content))
    return stream_response(
        stream_graph(
            run_id=run_id,
            conversation_id=conversation_id,
            project_id=project_id,
            user_id=user.sub,
            request=request,
            input_value={"messages": graph_history},
        )
    )


@router.post(
    "/conversations/{conversation_id}/runs/{run_id}/decision",
    dependencies=[Depends(require_enabled)],
)
async def decide_action(
    project_id: int,
    conversation_id: UUID,
    run_id: UUID,
    body: ActionDecision,
    request: Request,
    user: Annotated[UserPayload, Depends(get_current_user)],
) -> StreamingResponse:
    await authorized_chat(project_id, user.sub, conversation_id)
    async with UnitOfWork() as uow:
        session = uow.session
        if session is None:
            raise RuntimeError("UnitOfWork has not been entered")
        run = await session.get(AssistantRun, run_id)
        if run is None or run.conversation_id != conversation_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
        repository = AssistantRepository(session)
        claimed = await repository.claim_pending(
            run_id, "executing" if body.approve else "rejected"
        )
        if not claimed:
            raise HTTPException(status.HTTP_409_CONFLICT, "Action already resolved")
    return stream_response(
        stream_graph(
            run_id=run_id,
            conversation_id=conversation_id,
            project_id=project_id,
            user_id=user.sub,
            request=request,
            input_value=Command(resume=body.approve),
            approved=body.approve,
        )
    )
