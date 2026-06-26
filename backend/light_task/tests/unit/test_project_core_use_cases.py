from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.projects.constants import ProjectRole
from src.projects.dto import (
    CreateProjectCommand,
    DeleteProjectCommand,
    UpdateProjectCommand,
)
from src.projects.events import ProjectCreated, ProjectDeleted, ProjectUpdated
from src.projects.repository import ProjectRepository
from src.projects.use_cases import (
    CreateProjectUseCase,
    DeleteProjectUseCase,
    UpdateProjectUseCase,
)


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.added_all: list[object] = []
        self.deleted: list[object] = []
        self.execute_count = 0
        self.commit_count = 0
        self.refresh_count = 0
        self.flush_count = 0

    def add(self, instance: object) -> None:
        self.added.append(instance)

    def add_all(self, instances: list[object]) -> None:
        self.added_all.extend(instances)

    async def delete(self, instance: object) -> None:
        self.deleted.append(instance)

    async def execute(self, statement):
        self.execute_count += 1
        return None

    async def commit(self) -> None:
        self.commit_count += 1

    async def refresh(self, instance: object) -> None:
        self.refresh_count += 1

    async def flush(self) -> None:
        self.flush_count += 1


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


class FakeProjectRepository:
    def __init__(self, session: object) -> None:
        now = datetime.now(timezone.utc)
        self.project = SimpleNamespace(
            id=123,
            name="Project",
            description=None,
            color="#3B82F6",
            owner_id=7,
            created_at=now,
            updated_at=now,
        )

    def add_project(self, **kwargs):
        self.project.name = kwargs["name"]
        self.project.description = kwargs["description"]
        self.project.color = kwargs["color"]
        self.project.owner_id = kwargs["owner_id"]
        return self.project

    def save_project(self, project: object) -> None:
        return None

    async def delete_project(self, project: object) -> None:
        return None

    async def get_project(self, project_id: int):
        self.project.id = project_id
        return self.project

    async def get_member(self, *, project_id: int, user_id: int, with_user: bool = False):
        return SimpleNamespace(role=ProjectRole.OWNER)

    def add_member(self, **kwargs):
        return SimpleNamespace(**kwargs)

    def add_tags(self, tags: list[object]) -> None:
        return None

    async def get_project_member_user_ids(self, project_id: int) -> list[int]:
        return [7, 8]

    async def refresh_project(self, project: object) -> None:
        return None

    async def flush(self) -> None:
        return None


@pytest.mark.asyncio
async def test_project_repository_methods_do_not_commit() -> None:
    session = FakeSession()
    repository = ProjectRepository(session)  # type: ignore[arg-type]
    project = SimpleNamespace(id=1)

    repository.add_project(
        name="Project",
        description=None,
        color="#3B82F6",
        owner_id=7,
    )
    repository.save_project(project)  # type: ignore[arg-type]
    repository.add_member(project_id=1, user_id=7, role=ProjectRole.OWNER)
    repository.add_tags([])
    await repository.delete_project(project)  # type: ignore[arg-type]
    await repository.flush()
    await repository.refresh_project(project)  # type: ignore[arg-type]

    assert session.added
    assert session.deleted == [project]
    assert session.commit_count == 0
    assert session.flush_count == 1
    assert session.refresh_count == 1


@pytest.mark.asyncio
async def test_create_project_use_case_registers_project_created_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = FakeUnitOfWork()
    monkeypatch.setattr("src.projects.use_cases.ProjectRepository", FakeProjectRepository)
    use_case = CreateProjectUseCase(lambda: uow)  # type: ignore[arg-type]

    result = await use_case.execute(
        CreateProjectCommand(
            owner_id=7,
            name="Project",
            description=None,
            color="#3B82F6",
            client_mutation_id="mutation-1",
        )
    )

    assert result.id == 123
    assert result.current_user_role == ProjectRole.OWNER
    assert len(uow.events) == 1
    event = uow.events[0]
    assert isinstance(event, ProjectCreated)
    assert event.user_id == 7
    assert event.actor_user_id == 7
    assert event.project_id == 123
    assert event.client_mutation_id == "mutation-1"


@pytest.mark.asyncio
async def test_update_project_use_case_registers_project_updated_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = FakeUnitOfWork()
    monkeypatch.setattr("src.projects.use_cases.ProjectRepository", FakeProjectRepository)
    use_case = UpdateProjectUseCase(lambda: uow)  # type: ignore[arg-type]

    result = await use_case.execute(
        UpdateProjectCommand(
            project_id=123,
            actor_user_id=7,
            changes={"name": "Renamed"},
            client_mutation_id="mutation-2",
        )
    )

    assert result.id == 123
    assert result.name == "Renamed"
    assert len(uow.events) == 1
    event = uow.events[0]
    assert isinstance(event, ProjectUpdated)
    assert event.actor_user_id == 7
    assert event.project_id == 123
    assert event.client_mutation_id == "mutation-2"


@pytest.mark.asyncio
async def test_delete_project_use_case_registers_project_deleted_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = FakeUnitOfWork()
    monkeypatch.setattr("src.projects.use_cases.ProjectRepository", FakeProjectRepository)
    use_case = DeleteProjectUseCase(lambda: uow)  # type: ignore[arg-type]

    await use_case.execute(
        DeleteProjectCommand(
            project_id=123,
            actor_user_id=7,
            client_mutation_id="mutation-3",
        )
    )

    assert len(uow.events) == 1
    event = uow.events[0]
    assert isinstance(event, ProjectDeleted)
    assert event.affected_user_ids == [7, 8]
    assert event.actor_user_id == 7
    assert event.project_id == 123
    assert event.client_mutation_id == "mutation-3"
