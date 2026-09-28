from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.boards.dto import DeleteTaskCommand, UpdateTaskCommand
from src.boards.events import TaskDeleted, TaskUpdated
from src.boards.repository import BoardRepository
from src.boards.use_cases import DeleteTaskUseCase, UpdateTaskUseCase
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


class FakeTaskRepository:
    def __init__(self, session: object) -> None:
        self.task = SimpleNamespace(
            id=123,
            project_id=1,
            column_id=2,
            assignee_id=None,
            title="Initial",
            tags=[],
        )
        self.deleted: list[object] = []

    async def get_task_for_update(self, task_id: int):
        return self.task

    async def get_project_member(self, *, project_id: int, user_id: int):
        return SimpleNamespace(role=ProjectRole.OWNER)

    async def project_member_exists(self, *, project_id: int, user_id: int) -> bool:
        return True

    async def list_tags_by_ids(self, *, project_id: int, tag_ids: list[int]):
        return [SimpleNamespace(id=tag_id) for tag_id in tag_ids]

    def save_task(self, task) -> None:
        self.task = task

    async def delete_task(self, task) -> None:
        self.deleted.append(task)

    async def touch_project(self, project_id: int) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def get_task_with_tags(self, task_id: int):
        return self.task


@pytest.mark.asyncio
async def test_task_repository_save_and_delete_do_not_commit() -> None:
    session = FakeSession()
    repository = BoardRepository(session)  # type: ignore[arg-type]
    task = SimpleNamespace(id=1)

    repository.save_task(task)  # type: ignore[arg-type]
    await repository.delete_task(task)  # type: ignore[arg-type]
    await repository.touch_project(1)

    assert session.added == [task]
    assert session.deleted == [task]
    assert session.execute_count == 1
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_update_task_use_case_registers_task_updated_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = FakeUnitOfWork()
    monkeypatch.setattr("src.boards.use_cases.BoardRepository", FakeTaskRepository)
    use_case = UpdateTaskUseCase(lambda: uow)  # type: ignore[arg-type]

    result = await use_case.execute(
        UpdateTaskCommand(
            task_id=123,
            actor_user_id=7,
            changes={"title": "Updated"},
            tag_ids=[10],
            client_mutation_id="mutation-1",
        )
    )

    assert result.id == 123
    assert result.title == "Updated"
    assert [tag.id for tag in result.tags] == [10]
    assert len(uow.events) == 1
    event = uow.events[0]
    assert isinstance(event, TaskUpdated)
    assert event.task_id == 123
    assert event.actor_user_id == 7
    assert event.project_id == 1
    assert event.client_mutation_id == "mutation-1"


@pytest.mark.asyncio
async def test_add_and_remove_one_tag_preserves_other_task_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = FakeUnitOfWork()
    repository = FakeTaskRepository(uow.session)
    repository.task.tags = [SimpleNamespace(id=10), SimpleNamespace(id=11)]
    monkeypatch.setattr("src.boards.use_cases.BoardRepository", lambda session: repository)
    use_case = UpdateTaskUseCase(lambda: uow)  # type: ignore[arg-type]

    added = await use_case.execute(
        UpdateTaskCommand(task_id=123, actor_user_id=7, changes={}, add_tag_id=12)
    )
    assert [tag.id for tag in added.tags] == [10, 11, 12]

    removed = await use_case.execute(
        UpdateTaskCommand(task_id=123, actor_user_id=7, changes={}, remove_tag_id=11)
    )
    assert [tag.id for tag in removed.tags] == [10, 12]


@pytest.mark.asyncio
async def test_delete_task_use_case_registers_task_deleted_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = FakeUnitOfWork()
    monkeypatch.setattr("src.boards.use_cases.BoardRepository", FakeTaskRepository)
    use_case = DeleteTaskUseCase(lambda: uow)  # type: ignore[arg-type]

    await use_case.execute(
        DeleteTaskCommand(
            task_id=123,
            actor_user_id=7,
            client_mutation_id="mutation-1",
        )
    )

    assert len(uow.events) == 1
    event = uow.events[0]
    assert isinstance(event, TaskDeleted)
    assert event.task_id == 123
    assert event.column_id == 2
    assert event.actor_user_id == 7
    assert event.project_id == 1
    assert event.client_mutation_id == "mutation-1"
