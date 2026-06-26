from __future__ import annotations

from typing import Protocol

from src.boards.models import Task
from src.errors import ErrorCode
from src.shared.errors import ConflictError

POSITION_GAP = 65536.0
MIN_POSITION_DELTA = 0.001


class TaskOrderingRepository(Protocol):
    async def get_first_task_position_for_update(self, column_id: int) -> float | None: ...

    async def get_anchor_task_position_for_update(
        self,
        *,
        column_id: int,
        after_task_id: int,
    ) -> float | None: ...

    async def get_next_task_position_for_update(
        self,
        *,
        column_id: int,
        anchor_position: float,
    ) -> float | None: ...

    async def list_column_tasks_for_update(self, column_id: int) -> list[Task]: ...

    async def flush(self) -> None: ...


class TaskOrdering:
    def __init__(self, repository: TaskOrderingRepository) -> None:
        self._repository = repository

    async def calculate_new_position(
        self,
        *,
        column_id: int,
        after_task_id: int | None,
    ) -> float | None:
        if after_task_id is None:
            first_position = await self._repository.get_first_task_position_for_update(column_id)
            if first_position is None:
                return POSITION_GAP

            new_position = first_position / 2.0
            return new_position if new_position > MIN_POSITION_DELTA else None

        anchor_position = await self._repository.get_anchor_task_position_for_update(
            column_id=column_id,
            after_task_id=after_task_id,
        )
        if anchor_position is None:
            raise ConflictError(ErrorCode.ANCHOR_TASK_NOT_FOUND)

        next_position = await self._repository.get_next_task_position_for_update(
            column_id=column_id,
            anchor_position=anchor_position,
        )
        if next_position is None:
            return anchor_position + POSITION_GAP

        delta = next_position - anchor_position
        if delta <= MIN_POSITION_DELTA:
            return None

        return anchor_position + (delta / 2.0)

    async def rebalance_column(self, column_id: int) -> None:
        tasks = await self._repository.list_column_tasks_for_update(column_id)
        for index, task in enumerate(tasks):
            task.position = (index + 1) * POSITION_GAP

        await self._repository.flush()
