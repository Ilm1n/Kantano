from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from src.assistant.contracts import WriteToolName

MAX_ACTIONS = 10
REFERENCE = re.compile(r"^\$([a-zA-Z][a-zA-Z0-9_-]*)\.(task_id|column_id|tag_id)$")
RESULT_FIELDS = {"CreateColumn": "column_id", "CreateTask": "task_id", "CreateTag": "tag_id"}
ID_FIELDS = {
    "task_id": "task_id",
    "column_id": "column_id",
    "new_column_id": "column_id",
    "before_column_id": "column_id",
    "tag_id": "tag_id",
    "tag_ids": "tag_id",
}


class PlanStep(BaseModel):
    id: str = Field(
        pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$",
        max_length=40,
        description="Unique step name in this plan, e.g. column or task1; used by later references",
    )
    tool: WriteToolName = Field(description="Name of the write tool to execute for this step")
    args: dict[str, Any] = Field(
        description="Named tool's arguments. Existing IDs are integers; creations from earlier steps use $step_id.column_id, $step_id.task_id or $step_id.tag_id in compatible ID fields, including tag_ids."
    )


class ExecutePlan(BaseModel):
    """Propose an ordered plan of up to 10 changes for one confirmation.

    Use for multiple or dependent changes. Example: CreateColumn (id=column), then
    CreateTask with column_id='$column.column_id'. Existing IDs come from read tools.
    Each step uses its named tool's schema. After approval, returns an actions list
    with per-step results. On failure or stop, completed changes remain; later steps
    are skipped. This is not an all-or-nothing transaction.
    """

    steps: list[PlanStep] = Field(
        min_length=1,
        max_length=MAX_ACTIONS,
        description="All requested changes in execution order; references only target earlier creation steps",
    )


def validate_plan(
    args: dict[str, Any], validate_step: Callable[[str, dict[str, Any]], dict[str, Any]]
) -> dict[str, Any]:
    plan = ExecutePlan.model_validate(args)
    previous: dict[str, str] = {}
    steps: list[dict[str, Any]] = []
    for step in plan.steps:
        if step.id in previous:
            raise ValueError("Step IDs must be unique")
        placeholders: dict[str, Any] = {}
        references: dict[str, Any] = {}
        for field, value in step.args.items():
            items = value if isinstance(value, list) else [value]
            has_reference = False
            replaced: list[Any] = []
            for item in items:
                if isinstance(item, str) and item.startswith("$") and field in ID_FIELDS:
                    match = REFERENCE.fullmatch(item)
                    if (
                        match is None
                        or match[2] != ID_FIELDS[field]
                        or RESULT_FIELDS.get(previous.get(match[1], "")) != match[2]
                    ):
                        raise ValueError(
                            "References must use a compatible entity created by an earlier step"
                        )
                    has_reference = True
                    replaced.append(1)
                else:
                    replaced.append(item)
            placeholders[field] = replaced if isinstance(value, list) else replaced[0]
            if has_reference:
                references[field] = value
        validated = validate_step(step.tool, placeholders)
        validated.update(references)
        steps.append({"id": step.id, "tool": step.tool, "args": validated})
        previous[step.id] = step.tool
    return {"steps": steps}


def resolve_step(args: dict[str, Any], results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    def resolve(field: str, value: Any) -> Any:
        match = (
            REFERENCE.fullmatch(value) if isinstance(value, str) and field in ID_FIELDS else None
        )
        return results[match[1]][match[2]] if match else value

    return {
        field: [resolve(field, item) for item in value]
        if isinstance(value, list)
        else resolve(field, value)
        for field, value in args.items()
    }
