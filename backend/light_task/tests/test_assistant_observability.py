from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from test_assistant_lifecycle import create_chat
from test_assistant_project_tools import NoopCache, RecordingPublisher

from src.assistant import graph as graph_module
from src.assistant.dependencies import make_assistant_tools
from src.assistant.dto import DecideActionCommand, StartRunCommand
from src.assistant.provider import ModelAnswer, TokenUsage
from src.assistant.runtime import AssistantRuntime
from src.assistant.use_cases import AssistantRunLifecycle, DecideActionUseCase, StartRunUseCase
from src.db.unit_of_work import UnitOfWork
from src.observability.metrics import ApplicationMetrics, get_active_metrics, set_active_metrics
from src.shared.errors import ConflictError


@pytest.mark.parametrize("missing", [False, True])
def test_approval_resume_counts_one_run_and_combines_usage(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    missing: bool,
) -> None:
    scope, _, _ = create_chat(client, monkeypatch)
    metrics = ApplicationMetrics()
    previous = get_active_metrics()
    set_active_metrics(metrics)

    async def exercise() -> None:
        replies = iter(
            [
                ModelAnswer(
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "CreateColumn",
                                "args": {"name": "Metrics"},
                                "id": "proposal",
                            }
                        ],
                    ),
                    "test",
                    "model",
                    False,
                    1,
                    None if missing else TokenUsage(10, 2),
                ),
                ModelAnswer(
                    AIMessage(content="Rejected"), "test", "model", False, 1, TokenUsage(20, 3)
                ),
            ]
        )

        async def answer(*args: Any) -> ModelAnswer:
            return next(replies)

        monkeypatch.setattr(graph_module, "call_model", answer)
        saver = InMemorySaver()

        @asynccontextmanager
        async def checkpointer() -> AsyncIterator[InMemorySaver]:
            yield saver

        runtime = AssistantRuntime(
            lambda s: make_assistant_tools(s, RecordingPublisher(), NoopCache()),  # type: ignore[arg-type]
            AssistantRunLifecycle(UnitOfWork),
            checkpointer,  # type: ignore[arg-type]
        )
        execution = await StartRunUseCase(UnitOfWork).execute(
            StartRunCommand(**vars(scope), content="Create column")
        )
        first = [event async for event in runtime.stream(execution)]
        proposal = next(data["action"] for name, data in first if name == "approval_required")
        assert (
            metrics.registry.get_sample_value(
                "kantano_assistant_runs_total", {"status": "rejected"}
            )
            is None
        )
        command = DecideActionCommand(
            **vars(scope), run_id=execution.run_id, action_id=proposal["action_id"], approve=False
        )
        resumed = await DecideActionUseCase(UnitOfWork).execute(command)
        second = [event async for event in runtime.stream(resumed)]
        assert second[-1][1]["status"] == "rejected"
        assert (
            metrics.registry.get_sample_value(
                "kantano_assistant_runs_total", {"status": "rejected"}
            )
            == 1
        )
        # A duplicate confirmation cannot emit another terminal outcome or sample.
        with pytest.raises(ConflictError):
            await DecideActionUseCase(UnitOfWork).execute(command)
        histogram = metrics.assistant_run_tokens.collect()[0]
        counts = [sample.value for sample in histogram.samples if sample.name.endswith("_count")]
        sums = [sample.value for sample in histogram.samples if sample.name.endswith("_sum")]
        assert counts == ([] if missing else [1])
        assert sums == ([] if missing else [35])
        assert not metrics.assistant_tool_calls.collect()[0].samples
        await AssistantRunLifecycle(UnitOfWork).interrupt(execution.run_id)
        assert (
            metrics.registry.get_sample_value(
                "kantano_assistant_runs_total", {"status": "rejected"}
            )
            == 1
        )

    try:
        asyncio.run(exercise())
    finally:
        set_active_metrics(previous)
