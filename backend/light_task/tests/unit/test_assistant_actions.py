from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from src.assistant import graph as graph_module
from src.assistant.provider import ModelAnswer
from src.assistant.tools import CreateTask, UpdateTask
from src.errors import ErrorCode
from src.shared.errors import BadRequestError

pytestmark = pytest.mark.no_infra


class RecordingTools:
    def __init__(self) -> None:
        self.writes: list[dict[str, Any]] = []

    async def execute_write(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        self.writes.append(args)
        return {"kind": "created", "task_id": len(self.writes)}


def model_answer(message: AIMessage) -> ModelAnswer:
    return ModelAnswer(message, "test", "test", False, 0)


@pytest.mark.asyncio
async def test_four_writes_require_four_separate_approvals(monkeypatch: pytest.MonkeyPatch) -> None:
    tools = RecordingTools()
    saved: list[list[dict[str, Any]]] = []
    invocations = 0

    async def call_model(messages: list[BaseMessage], schemas: list[type]) -> ModelAnswer:
        nonlocal invocations
        invocations += 1
        if invocations == 1:
            return model_answer(
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "CreateTask",
                            "id": f"call-{i}",
                            "args": {"title": f"Task {i}", "column_id": 1, "priority": "Высокий"},
                        }
                        for i in range(4)
                    ],
                )
            )
        assert {m.tool_call_id for m in messages if isinstance(m, ToolMessage)} == {
            f"call-{i}" for i in range(4)
        }
        return model_answer(AIMessage(content="Finished"))

    async def record(outcomes: list[dict[str, Any]]) -> None:
        saved.append(outcomes)

    monkeypatch.setattr(graph_module, "call_model", call_model)
    graph = graph_module.build_graph(InMemorySaver(), tools, record)
    config = {"configurable": {"thread_id": str(uuid4())}, "recursion_limit": 100}
    await graph.ainvoke({"messages": [HumanMessage(content="Create four tasks")]}, config)
    assert tools.writes == []
    action_ids: set[str] = set()
    for i in range(4):
        snapshot = await graph.aget_state(config)
        proposal = snapshot.values["proposed_action"]
        assert proposal["args"]["priority"] == "HIGH"
        action_ids.add(proposal["action_id"])
        assert any(task.interrupts for task in snapshot.tasks)
        # Reconstruct the graph, as each HTTP approval uses a fresh graph instance.
        graph = graph_module.build_graph(graph.checkpointer, tools, record)
        await graph.ainvoke(Command(resume=True), config)
        assert len(tools.writes) == i + 1
    assert len(action_ids) == 4
    assert [len(items) for items in saved] == [1, 2, 3, 4]
    assert not (await graph.aget_state(config)).next


@pytest.mark.asyncio
async def test_rejection_skips_only_that_action(monkeypatch: pytest.MonkeyPatch) -> None:
    tools = RecordingTools()
    replies = iter(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "CreateTask", "id": str(i), "args": {"title": str(i), "column_id": 1}}
                    for i in range(2)
                ],
            ),
            AIMessage(content="Finished"),
        ]
    )

    async def call_model(*args: Any) -> ModelAnswer:
        return model_answer(next(replies))

    monkeypatch.setattr(graph_module, "call_model", call_model)
    graph = graph_module.build_graph(InMemorySaver(), tools)
    config = {"configurable": {"thread_id": str(uuid4())}}
    await graph.ainvoke({"messages": [HumanMessage(content="Create tasks")]}, config)
    await graph.ainvoke(Command(resume=False), config)
    assert tools.writes == []
    await graph.ainvoke(Command(resume=True), config)
    assert [args["title"] for args in tools.writes] == ["1"]


@pytest.mark.asyncio
async def test_invalid_arguments_are_repaired_before_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = RecordingTools()
    replies = iter(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "CreateTask",
                        "id": "invalid",
                        "args": {"title": "Task", "column_id": 1, "priority": "INVALID"},
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "CreateTask",
                        "id": "valid",
                        "args": {"title": "Task", "column_id": 1, "priority": "HIGH"},
                    }
                ],
            ),
        ]
    )

    async def call_model(*args: Any) -> ModelAnswer:
        return model_answer(next(replies))

    monkeypatch.setattr(graph_module, "call_model", call_model)
    graph = graph_module.build_graph(InMemorySaver(), tools)
    config = {"configurable": {"thread_id": str(uuid4())}}
    await graph.ainvoke({"messages": [HumanMessage(content="Create task")]}, config)
    snapshot = await graph.aget_state(config)
    assert snapshot.values["proposed_action"]["tool_call_id"] == "valid"
    assert tools.writes == []


@pytest.mark.parametrize("schema", [CreateTask, UpdateTask])
@pytest.mark.parametrize("priority", ["Высокий", "high", "HIGH"])
def test_task_priority_aliases(schema: type, priority: str) -> None:
    data = schema.model_validate(
        {"title": "Task", "column_id": 1, "task_id": 1, "priority": priority}
    )
    assert data.priority.value == "HIGH"


@pytest.mark.asyncio
async def test_domain_rejection_is_a_known_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class RejectingTools(RecordingTools):
        async def execute_write(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
            raise BadRequestError(ErrorCode.INVALID_TAG_IDS)

    replies = iter(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "CreateTask", "id": "write", "args": {"title": "Task", "column_id": 1}}
                ],
            ),
            AIMessage(content="Failed"),
        ]
    )

    async def call_model(*args: Any) -> ModelAnswer:
        return model_answer(next(replies))

    monkeypatch.setattr(graph_module, "call_model", call_model)
    graph = graph_module.build_graph(InMemorySaver(), RejectingTools())
    config = {"configurable": {"thread_id": str(uuid4())}}
    await graph.ainvoke({"messages": [HumanMessage(content="Create task")]}, config)
    state = await graph.ainvoke(Command(resume=True), config)
    assert state["action_results"][0]["status"] == "failed"
    assert state["action_results"][0]["error_code"] == "INVALID_TAG_IDS"
