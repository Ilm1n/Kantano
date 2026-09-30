from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import asdict
from time import perf_counter
from typing import Any, Literal, cast
from uuid import UUID

import anyio
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command

from src.assistant.checkpoints import open_checkpointer
from src.assistant.dto import ProjectScope, RunExecution, RunMetadata
from src.assistant.graph import AssistantState, RunStoppedError, build_graph
from src.assistant.tools import AssistantTools
from src.assistant.use_cases import AssistantRunLifecycle
from src.config import settings
from src.observability.metrics import record_assistant_run_tokens

logger = logging.getLogger(__name__)
StreamEvent = tuple[
    Literal["run", "delta", "reset", "approval_required", "done", "error"], dict[str, Any]
]


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


class AssistantRuntime:
    def __init__(
        self,
        tools_factory: Callable[[ProjectScope], AssistantTools],
        lifecycle: AssistantRunLifecycle,
        checkpointer_factory: Callable[
            [], AbstractAsyncContextManager[AsyncPostgresSaver]
        ] = open_checkpointer,
    ) -> None:
        self._tools_factory = tools_factory
        self._lifecycle = lifecycle
        self._checkpointer_factory = checkpointer_factory

    async def interrupt(self, run_id: UUID) -> None:
        await self._lifecycle.interrupt(run_id)

    async def stream(self, execution: RunExecution) -> AsyncGenerator[StreamEvent, None]:
        start = perf_counter()
        run_id = execution.run_id
        conversation_id = execution.scope.conversation_id
        tools = self._tools_factory(execution.scope)
        config: RunnableConfig = {
            "configurable": {"thread_id": str(run_id)},
            "recursion_limit": 100,
        }
        input_value = (
            Command(resume=execution.approve)
            if execution.approve is not None
            else {
                "messages": [
                    HumanMessage(content=message.content)
                    if message.role == "user"
                    else AIMessage(content=message.content)
                    for message in execution.history
                ]
            }
        )

        async def record_action_result(outcomes: list[dict[str, Any]], executing: bool) -> None:
            with anyio.fail_after(10, shield=True):
                await self._lifecycle.record_results(execution, outcomes, executing)
            outcome = outcomes[-1]
            logger.info(
                "assistant_action",
                extra={
                    "run_id": str(run_id),
                    "conversation_id": str(conversation_id),
                    "tool": outcome["tool"],
                    "result": outcome["status"],
                },
            )

        try:
            yield "run", {"run_id": str(run_id), "status": "running"}
            async with self._checkpointer_factory() as saver:
                graph = build_graph(
                    saver,
                    tools,
                    on_action_result=record_action_result,
                    should_stop=lambda: self._lifecycle.stop_requested(run_id),
                )
                streamed_node_text = ""
                async for mode, event in graph.astream(
                    input_value, config, stream_mode=["messages", "updates"]
                ):
                    if mode == "messages":
                        chunk, metadata = cast(tuple[BaseMessage, dict[str, Any]], event)
                        if metadata.get("langgraph_node") == "agent" and isinstance(
                            chunk, AIMessageChunk
                        ):
                            token = public_text(chunk.content)
                            if token:
                                streamed_node_text += token
                                yield "delta", {"text": token}
                    elif mode == "updates" and "agent" in event:
                        update = cast(dict[str, dict[str, Any]], event)["agent"]
                        answer = update["messages"][-1]
                        if isinstance(answer, AIMessage) and not answer.tool_calls:
                            content = public_text(answer.content)
                            if update.get("last_fallback_used"):
                                yield "reset", {}
                                yield "delta", {"text": content}
                            elif not streamed_node_text and content:
                                yield "delta", {"text": content}
                        streamed_node_text = ""
                snapshot = await graph.aget_state(config)
                state = cast(AssistantState, snapshot.values)
                run_metadata = RunMetadata(
                    provider=state.get("provider"),
                    model=state.get("model"),
                    step_count=state.get("step_count", 0),
                    fallback_used=state.get("fallback_used", False),
                )
                if any(task.interrupts for task in snapshot.tasks):
                    action = state.get("proposed_action")
                    if action is None:
                        raise RuntimeError("Missing pending action")
                    final_status = await self._lifecycle.pending(execution, action, run_metadata)
                    if final_status == "pending":
                        yield "approval_required", {"action": action, **asdict(run_metadata)}
                    else:
                        yield (
                            "done",
                            {"status": final_status, "message": "", **asdict(run_metadata)},
                        )
                else:
                    messages = state.get("messages", [])
                    answer = messages[-1] if messages else None
                    content = public_text(answer.content) if isinstance(answer, AIMessage) else ""
                    final_status, content = await self._lifecycle.complete(
                        execution,
                        content,
                        state.get("action_results", []),
                        state.get("references", []),
                        run_metadata,
                    )
                    if state.get("reported_usage_calls", 0) and not state.get(
                        "missing_usage_calls", 0
                    ):
                        record_assistant_run_tokens(
                            settings.assistant.mode,
                            state.get("input_tokens", 0) + state.get("output_tokens", 0),
                        )
                    yield (
                        "done",
                        {"status": final_status, "message": content, **asdict(run_metadata)},
                    )
                logger.info(
                    "assistant_run",
                    extra={
                        "run_id": str(run_id),
                        "conversation_id": str(conversation_id),
                        "provider": run_metadata.provider,
                        "model": run_metadata.model,
                        "steps": run_metadata.step_count,
                        "llm_duration_ms": state.get("llm_duration_ms", 0),
                        "fallback": run_metadata.fallback_used,
                        "status": final_status,
                        "segment_duration_ms": int((perf_counter() - start) * 1000),
                        "input_tokens": state.get("input_tokens", 0),
                        "output_tokens": state.get("output_tokens", 0),
                        "reported_usage_calls": state.get("reported_usage_calls", 0),
                        "missing_usage_calls": state.get("missing_usage_calls", 0),
                    },
                )
        except RunStoppedError:
            with anyio.fail_after(10, shield=True):
                message = await self._lifecycle.cancel(execution)
            logger.info(
                "assistant_run_stopped",
                extra={
                    "run_id": str(run_id),
                    "conversation_id": str(conversation_id),
                },
            )
            yield "done", {"status": "cancelled", "message": message}
        except Exception as exc:
            with anyio.fail_after(10, shield=True):
                message = await self._lifecycle.fail(execution)
            cause = exc
            while cause.__cause__ is not None:
                cause = cause.__cause__
            logger.error(
                "assistant_run_failed",
                extra={
                    "run_id": str(run_id),
                    "conversation_id": str(conversation_id),
                    "error_type": type(exc).__name__,
                    "cause_type": type(cause).__name__,
                },
            )
            yield "error", {"message": message, "run_id": str(run_id)}
