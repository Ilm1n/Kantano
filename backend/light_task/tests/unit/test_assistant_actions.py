from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic import ValidationError

from src.assistant import graph as graph_module
from src.assistant.provider import ModelAnswer
from src.assistant.tools import CreateTask, UpdateTask, validate_write
from src.errors import ErrorCode
from src.shared.errors import BadRequestError

pytestmark = pytest.mark.no_infra


class RecordingTools:
    def __init__(self) -> None:
        self.writes: list[dict[str, Any]] = []

    async def execute_write(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        self.writes.append(args)
        if name == "CreateColumn":
            return {"kind": "column_created", "column_id": 42, "name": args["name"]}
        if name == "CreateTag":
            return {"kind": "tag_created", "tag_id": 7, "name": args["name"]}
        return {"kind": "created", "task_id": len(self.writes), "title": args.get("title", "Task")}

    async def describe_action(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        return {"steps": args["steps"]} if name == "ExecutePlan" else {}


def model_answer(message: AIMessage) -> ModelAnswer:
    return ModelAnswer(message, "test", "test", False, 0)


@pytest.mark.asyncio
async def test_four_writes_require_one_plan_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    tools = RecordingTools()
    saved: list[list[dict[str, Any]]] = []
    executing_states: list[bool] = []
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

    async def record(outcomes: list[dict[str, Any]], executing: bool) -> None:
        saved.append(list(outcomes))
        executing_states.append(executing)

    monkeypatch.setattr(graph_module, "call_model", call_model)
    graph = graph_module.build_graph(InMemorySaver(), tools, record)
    config = {"configurable": {"thread_id": str(uuid4())}, "recursion_limit": 100}
    await graph.ainvoke({"messages": [HumanMessage(content="Create four tasks")]}, config)
    assert tools.writes == []
    snapshot = await graph.aget_state(config)
    proposal = snapshot.values["proposed_action"]
    assert proposal["name"] == "ExecutePlan"
    assert len(proposal["args"]["steps"]) == 4
    assert all(step["args"]["priority"] == "HIGH" for step in proposal["args"]["steps"])
    assert any(task.interrupts for task in snapshot.tasks)
    graph = graph_module.build_graph(graph.checkpointer, tools, record)
    await graph.ainvoke(Command(resume=True), config)
    assert len(tools.writes) == 4
    assert [len(items) for items in saved] == [1, 2, 3, 4]
    assert executing_states == [True, True, True, False]
    assert not (await graph.aget_state(config)).next


@pytest.mark.asyncio
async def test_rejection_rejects_the_whole_plan(monkeypatch: pytest.MonkeyPatch) -> None:
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
    state = await graph.ainvoke(Command(resume=False), config)
    assert tools.writes == []
    assert [result["status"] for result in state["action_results"]] == ["rejected", "rejected"]
    assert not (await graph.aget_state(config)).next


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


@pytest.mark.parametrize(
    "reference", ["$later.column_id", "$column.task_id", "$column.invalid", "$task.column_id"]
)
def test_plan_rejects_forward_and_incompatible_references(reference: str) -> None:
    with pytest.raises((ValueError, ValidationError)):
        validate_write(
            "ExecutePlan",
            {
                "steps": [
                    {"id": "column", "tool": "CreateColumn", "args": {"name": "Work"}},
                    {
                        "id": "task",
                        "tool": "CreateTask",
                        "args": {"title": "Task", "column_id": reference},
                    },
                ]
            },
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_second", [False, True])
async def test_dependent_plan_resolves_results_and_stops_after_known_failure(
    monkeypatch: pytest.MonkeyPatch, fail_second: bool
) -> None:
    class PlanTools(RecordingTools):
        async def execute_write(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
            if fail_second and name == "CreateTag":
                raise BadRequestError(ErrorCode.TAG_ALREADY_EXISTS)
            return await super().execute_write(name, args)

    tools = PlanTools()
    replies = iter(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ExecutePlan",
                        "id": "plan",
                        "args": {
                            "steps": [
                                {"id": "column", "tool": "CreateColumn", "args": {"name": "Work"}},
                                {"id": "tag", "tool": "CreateTag", "args": {"name": "Feature"}},
                                {
                                    "id": "task",
                                    "tool": "CreateTask",
                                    "args": {
                                        "title": "Task",
                                        "column_id": "$column.column_id",
                                        "tag_ids": ["$tag.tag_id"],
                                    },
                                },
                                {
                                    "id": "update",
                                    "tool": "UpdateTask",
                                    "args": {"task_id": "$task.task_id", "priority": "HIGH"},
                                },
                            ]
                        },
                    }
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
    await graph.ainvoke({"messages": [HumanMessage(content="Build structure")]}, config)
    assert not tools.writes
    state = await graph.ainvoke(Command(resume=True), config)
    if fail_second:
        assert len(tools.writes) == 1
        assert [result["status"] for result in state["action_results"]] == [
            "completed",
            "failed",
            "skipped",
            "skipped",
        ]
    else:
        assert tools.writes[2]["column_id"] == 42
        assert tools.writes[2]["tag_ids"] == [7]
        assert tools.writes[3]["task_id"] == 3


@pytest.mark.asyncio
async def test_new_action_outside_approved_plan_needs_new_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = RecordingTools()
    replies = iter(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "CreateTask", "id": "first", "args": {"title": "One", "column_id": 1}}
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "CreateTask", "id": "second", "args": {"title": "Two", "column_id": 1}}
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
    first_id = (await graph.aget_state(config)).values["proposed_action"]["action_id"]
    await graph.ainvoke(Command(resume=True), config)
    snapshot = await graph.aget_state(config)
    assert snapshot.values["proposed_action"]["action_id"] != first_id
    assert len(tools.writes) == 1
    assert any(task.interrupts for task in snapshot.tasks)
    await graph.ainvoke(Command(resume=True), config)
    assert len(tools.writes) == 2


@pytest.mark.asyncio
async def test_multiple_plans_in_one_reply_keep_dependencies_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DistinctColumns(RecordingTools):
        async def execute_write(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
            result = await super().execute_write(name, args)
            if name == "CreateColumn":
                result["column_id"] = len(self.writes) + 100
            return result

    tools = DistinctColumns()
    calls = [
        {
            "name": "ExecutePlan",
            "id": str(i),
            "args": {
                "steps": [
                    {"id": "column", "tool": "CreateColumn", "args": {"name": f"Column {i}"}},
                    {
                        "id": "task",
                        "tool": "CreateTask",
                        "args": {"title": f"Task {i}", "column_id": "$column.column_id"},
                    },
                ]
            },
        }
        for i in range(2)
    ]
    replies = iter([AIMessage(content="", tool_calls=calls), AIMessage(content="Finished")])

    async def call_model(*args: Any) -> ModelAnswer:
        return model_answer(next(replies))

    monkeypatch.setattr(graph_module, "call_model", call_model)
    graph = graph_module.build_graph(InMemorySaver(), tools)
    config = {"configurable": {"thread_id": str(uuid4())}}
    await graph.ainvoke({"messages": [HumanMessage(content="Build structure")]}, config)
    await graph.ainvoke(Command(resume=True), config)
    assert tools.writes[1]["column_id"] == 101
    assert tools.writes[3]["column_id"] == 103
