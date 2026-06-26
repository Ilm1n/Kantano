from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.boards.dto import (
    CreateColumnCommand,
    DeleteColumnCommand,
    ReorderColumnsCommand,
    UpdateColumnCommand,
)
from src.boards.events import (
    ColumnCreated,
    ColumnDeleted,
    ColumnsReordered,
    ColumnUpdated,
)
from src.boards.repository import BoardRepository
from src.boards.use_cases import (
    CreateColumnUseCase,
    DeleteColumnUseCase,
    ReorderColumnsUseCase,
    UpdateColumnUseCase,
)
from src.projects.constants import ProjectRole


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.execute_count = 0
        self.commit_count = 0

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def delete(self, instance: object) -> None:
        self.deleted.append(instance)

    async def execute(self, statement):
        self.execute_count += 1
        return None

    async def commit(self) -> None:
        self.commit_count += 1


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.session = object()
        self.events: list[object] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        return False

    def collect_event(self, event: object) -> None:
        self.events.append(event)


class FakeBoardRepository:
    def __init__(self, session: object) -> None:
        self.column = SimpleNamespace(
            id=123,
            project_id=1,
            name="Todo",
            tasks_limit=None,
            position=65536.0,
        )
        self.columns = [
            SimpleNamespace(id=1, project_id=1, position=65536.0),
            SimpleNamespace(id=2, project_id=1, position=131072.0),
        ]

    async def get_project_member(self, *, project_id: int, user_id: int):
        return SimpleNamespace(role=ProjectRole.OWNER)

    async def get_max_column_position(self, project_id: int) -> float:
        return 0.0

    def add_column(self, **kwargs):
        return self.column

    async def get_column_in_project(self, *, project_id: int, column_id: int):
        self.column.id = column_id
        return self.column

    async def get_column_with_tasks(self, column_id: int):
        self.column.id = column_id
        return self.column

    def save_column(self, column: object) -> None:
        return None

    async def delete_column(self, column: object) -> None:
        return None

    async def list_project_columns_by_ids(self, *, project_id: int, column_ids: list[int]):
        return self.columns

    async def touch_project(self, project_id: int) -> None:
        return None

    async def flush(self) -> None:
        return None


@pytest.mark.asyncio
async def test_column_repository_methods_do_not_commit() -> None:
    session = FakeSession()
    repository = BoardRepository(session)  # type: ignore[arg-type]
    column = SimpleNamespace(id=1)

    repository.add_column(
        project_id=1,
        name="Todo",
        tasks_limit=None,
        position=65536.0,
    )
    repository.save_column(column)  # type: ignore[arg-type]
    await repository.delete_column(column)  # type: ignore[arg-type]
    await repository.touch_project(1)

    assert session.added
    assert session.deleted == [column]
    assert session.execute_count == 1
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_create_column_use_case_registers_column_created_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = FakeUnitOfWork()
    monkeypatch.setattr("src.boards.use_cases.BoardRepository", FakeBoardRepository)
    use_case = CreateColumnUseCase(lambda: uow)  # type: ignore[arg-type]

    result = await use_case.execute(
        CreateColumnCommand(
            project_id=1,
            actor_user_id=3,
            name="Todo",
            tasks_limit=None,
            client_mutation_id="mutation-1",
        )
    )

    assert result.id == 123
    assert len(uow.events) == 1
    event = uow.events[0]
    assert isinstance(event, ColumnCreated)
    assert event.column_id == 123
    assert event.actor_user_id == 3
    assert event.project_id == 1
    assert event.client_mutation_id == "mutation-1"


@pytest.mark.asyncio
async def test_update_column_use_case_registers_column_updated_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = FakeUnitOfWork()
    monkeypatch.setattr("src.boards.use_cases.BoardRepository", FakeBoardRepository)
    use_case = UpdateColumnUseCase(lambda: uow)  # type: ignore[arg-type]

    result = await use_case.execute(
        UpdateColumnCommand(
            project_id=1,
            column_id=123,
            actor_user_id=3,
            changes={"name": "Doing"},
            client_mutation_id="mutation-2",
        )
    )

    assert result.id == 123
    assert len(uow.events) == 1
    event = uow.events[0]
    assert isinstance(event, ColumnUpdated)
    assert event.column_id == 123
    assert event.actor_user_id == 3
    assert event.project_id == 1
    assert event.client_mutation_id == "mutation-2"


@pytest.mark.asyncio
async def test_delete_column_use_case_registers_column_deleted_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = FakeUnitOfWork()
    monkeypatch.setattr("src.boards.use_cases.BoardRepository", FakeBoardRepository)
    use_case = DeleteColumnUseCase(lambda: uow)  # type: ignore[arg-type]

    await use_case.execute(
        DeleteColumnCommand(
            project_id=1,
            column_id=123,
            actor_user_id=3,
            client_mutation_id="mutation-3",
        )
    )

    assert len(uow.events) == 1
    event = uow.events[0]
    assert isinstance(event, ColumnDeleted)
    assert event.column_id == 123
    assert event.actor_user_id == 3
    assert event.project_id == 1
    assert event.client_mutation_id == "mutation-3"


@pytest.mark.asyncio
async def test_reorder_columns_use_case_registers_columns_reordered_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = FakeUnitOfWork()
    monkeypatch.setattr("src.boards.use_cases.BoardRepository", FakeBoardRepository)
    use_case = ReorderColumnsUseCase(lambda: uow)  # type: ignore[arg-type]

    await use_case.execute(
        ReorderColumnsCommand(
            project_id=1,
            actor_user_id=3,
            column_ids=[2, 1],
            client_mutation_id="mutation-4",
        )
    )

    assert len(uow.events) == 1
    event = uow.events[0]
    assert isinstance(event, ColumnsReordered)
    assert event.column_ids == [2, 1]
    assert event.actor_user_id == 3
    assert event.project_id == 1
    assert event.client_mutation_id == "mutation-4"
