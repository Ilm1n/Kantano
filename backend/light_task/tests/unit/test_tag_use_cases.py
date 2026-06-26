from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.projects.constants import ProjectRole
from src.tags.dto import CreateTagCommand, DeleteTagCommand, UpdateTagCommand
from src.tags.events import TagCreated, TagDeleted, TagUpdated
from src.tags.repository import TagRepository
from src.tags.use_cases import CreateTagUseCase, DeleteTagUseCase, UpdateTagUseCase


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


class FakeTagRepository:
    def __init__(self, session: object) -> None:
        self.tag = SimpleNamespace(id=10, project_id=100, name="Backend", color="#9CA3AF")
        self.member = SimpleNamespace(role=ProjectRole.OWNER)

    async def get_project_member(self, *, project_id: int, user_id: int):
        return self.member

    async def get_tag(self, tag_id: int):
        return self.tag

    async def find_tag_by_name(self, *, project_id: int, name: str):
        return None

    def add_tag(self, tag) -> None:
        self.tag = tag

    def save_tag(self, tag) -> None:
        self.tag = tag

    async def delete_tag(self, tag) -> None:
        self.deleted_tag = tag

    async def touch_project(self, project_id: int) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def get_project_member_user_ids(self, project_id: int):
        return [1, 2]


@pytest.mark.asyncio
async def test_tag_repository_methods_do_not_commit() -> None:
    session = FakeSession()
    repository = TagRepository(session)  # type: ignore[arg-type]
    tag = SimpleNamespace(id=1)

    repository.add_tag(tag)  # type: ignore[arg-type]
    repository.save_tag(tag)  # type: ignore[arg-type]
    await repository.delete_tag(tag)  # type: ignore[arg-type]
    await repository.touch_project(1)

    assert session.added == [tag, tag]
    assert session.deleted == [tag]
    assert session.execute_count == 1
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_create_tag_use_case_registers_tag_created_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = FakeUnitOfWork()
    monkeypatch.setattr("src.tags.use_cases.TagRepository", FakeTagRepository)
    use_case = CreateTagUseCase(lambda: uow)  # type: ignore[arg-type]

    tag = await use_case.execute(
        CreateTagCommand(
            project_id=100,
            actor_user_id=1,
            name="Backend",
            color="#9CA3AF",
            client_mutation_id="mutation-1",
        )
    )

    assert tag.name == "Backend"
    assert len(uow.events) == 1
    event = uow.events[0]
    assert isinstance(event, TagCreated)
    assert event.tag is tag
    assert event.affected_user_ids == [1, 2]
    assert event.actor_user_id == 1
    assert event.project_id == 100
    assert event.client_mutation_id == "mutation-1"


@pytest.mark.asyncio
async def test_update_tag_use_case_registers_tag_updated_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = FakeUnitOfWork()
    monkeypatch.setattr("src.tags.use_cases.TagRepository", FakeTagRepository)
    use_case = UpdateTagUseCase(lambda: uow)  # type: ignore[arg-type]

    tag = await use_case.execute(
        UpdateTagCommand(
            tag_id=10,
            actor_user_id=1,
            changes={"name": "Frontend"},
            client_mutation_id="mutation-1",
        )
    )

    assert tag.name == "Frontend"
    assert len(uow.events) == 1
    event = uow.events[0]
    assert isinstance(event, TagUpdated)
    assert event.tag is tag
    assert event.affected_user_ids == [1, 2]
    assert event.actor_user_id == 1
    assert event.project_id == 100
    assert event.client_mutation_id == "mutation-1"


@pytest.mark.asyncio
async def test_delete_tag_use_case_registers_tag_deleted_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = FakeUnitOfWork()
    monkeypatch.setattr("src.tags.use_cases.TagRepository", FakeTagRepository)
    use_case = DeleteTagUseCase(lambda: uow)  # type: ignore[arg-type]

    await use_case.execute(
        DeleteTagCommand(
            tag_id=10,
            actor_user_id=1,
            client_mutation_id="mutation-1",
        )
    )

    assert len(uow.events) == 1
    event = uow.events[0]
    assert isinstance(event, TagDeleted)
    assert event.tag_id == 10
    assert event.affected_user_ids == [1, 2]
    assert event.actor_user_id == 1
    assert event.project_id == 100
    assert event.client_mutation_id == "mutation-1"
