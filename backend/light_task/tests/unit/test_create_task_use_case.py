from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from src.boards.constants import TaskPriority
from src.boards.dto import CreateTaskCommand
from src.boards.events import TaskCreated
from src.boards.repository import BoardRepository
from src.boards.use_cases import CreateTaskUseCase
from src.projects.constants import ProjectRole


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.execute_count = 0
        self.commit_count = 0

    def add(self, instance: object) -> None:
        self.added.append(instance)

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
        self.task = SimpleNamespace(id=123)

    async def get_column(self, column_id: int):
        return SimpleNamespace(id=column_id, project_id=1, tasks_limit=None)

    async def get_project_member(self, *, project_id: int, user_id: int):
        return SimpleNamespace(role=ProjectRole.OWNER)

    async def project_member_exists(self, *, project_id: int, user_id: int) -> bool:
        return True

    async def list_tags_by_ids(self, *, project_id: int, tag_ids: list[int]):
        return []

    async def get_max_task_position(self, column_id: int) -> float:
        return 0.0

    async def add_task(self, **kwargs):
        return self.task

    async def touch_project(self, project_id: int) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def get_task_with_tags(self, task_id: int):
        return self.task


@pytest.mark.asyncio
async def test_board_repository_methods_do_not_commit() -> None:
    session = FakeSession()
    repository = BoardRepository(session)  # type: ignore[arg-type]

    await repository.add_task(
        title="Task",
        description=None,
        priority=TaskPriority.MEDIUM,
        deadline_at=None,
        project_id=1,
        column_id=2,
        assignee_id=None,
        author_id=3,
        position=65536.0,
        tags=[],
    )
    await repository.touch_project(1)

    assert session.added
    assert session.execute_count == 1
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_create_task_use_case_registers_task_created_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = FakeUnitOfWork()
    monkeypatch.setattr("src.boards.use_cases.BoardRepository", FakeBoardRepository)
    use_case = CreateTaskUseCase(lambda: uow)  # type: ignore[arg-type]

    result = await use_case.execute(
        CreateTaskCommand(
            project_id=1,
            column_id=2,
            author_id=3,
            title="Task",
            description=None,
            priority=TaskPriority.MEDIUM,
            assignee_id=None,
            deadline_at=datetime.now(UTC),
            tag_ids=[],
            client_mutation_id="mutation-1",
        )
    )

    assert result.id == 123
    assert len(uow.events) == 1
    event = uow.events[0]
    assert isinstance(event, TaskCreated)
    assert event.task_id == 123
    assert event.actor_user_id == 3
    assert event.project_id == 1
    assert event.client_mutation_id == "mutation-1"
