from typing import Literal

RunStatus = Literal[
    "running", "pending", "executing", "completed", "rejected", "failed", "interrupted", "unknown"
]
ACTIVE_RUN_STATUSES = ("running", "pending", "executing")
EXECUTING_RUN_STATUSES = ("running", "executing")
WriteToolName = Literal[
    "CreateTask",
    "UpdateTask",
    "MoveTask",
    "CreateColumn",
    "RenameColumn",
    "MoveColumn",
    "CreateTag",
    "UpdateTag",
    "AddTagToTask",
    "RemoveTagFromTask",
]
ActionStatus = Literal["completed", "rejected", "failed", "skipped"]
ActionName = Literal[
    "CreateTask",
    "UpdateTask",
    "MoveTask",
    "CreateColumn",
    "RenameColumn",
    "MoveColumn",
    "CreateTag",
    "UpdateTag",
    "AddTagToTask",
    "RemoveTagFromTask",
    "ExecutePlan",
]
ActionKind = Literal[
    "created",
    "updated",
    "moved",
    "column_created",
    "column_renamed",
    "column_moved",
    "tag_created",
    "tag_updated",
    "tag_added_to_task",
    "tag_removed_from_task",
]
