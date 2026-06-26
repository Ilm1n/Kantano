from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.projects.constants import ProjectRole
from src.projects.dto import RemoveMemberCommand, UpdateMemberRoleCommand
from src.projects.events import MemberRemoved, MemberRoleChanged
from src.projects.repository import ProjectRepository
from src.projects.use_cases import RemoveMemberUseCase, UpdateMemberRoleUseCase


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


class FakeProjectRepository:
    def __init__(self, session: object) -> None:
        self.requester = SimpleNamespace(user_id=1, role=ProjectRole.OWNER)
        self.target = SimpleNamespace(
            id=10,
            project_id=100,
            user_id=2,
            role=ProjectRole.MEMBER,
        )
        self.deleted: list[object] = []

    async def get_member(self, *, project_id: int, user_id: int, with_user: bool = False):
        if user_id == 1:
            return self.requester
        if user_id == 2:
            return self.target
        return None

    def save_member(self, member) -> None:
        self.target = member

    async def delete_member(self, member) -> None:
        self.deleted.append(member)

    async def touch_project(self, project_id: int) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def get_project_member_user_ids(self, project_id: int):
        return [1]


@pytest.mark.asyncio
async def test_project_repository_save_and_delete_do_not_commit() -> None:
    session = FakeSession()
    repository = ProjectRepository(session)  # type: ignore[arg-type]
    member = SimpleNamespace(id=1)

    repository.save_member(member)  # type: ignore[arg-type]
    await repository.delete_member(member)  # type: ignore[arg-type]
    await repository.touch_project(1)

    assert session.added == [member]
    assert session.deleted == [member]
    assert session.execute_count == 1
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_remove_member_use_case_registers_member_removed_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = FakeUnitOfWork()
    monkeypatch.setattr("src.projects.use_cases.ProjectRepository", FakeProjectRepository)
    use_case = RemoveMemberUseCase(lambda: uow)  # type: ignore[arg-type]

    await use_case.execute(
        RemoveMemberCommand(
            project_id=100,
            user_id=2,
            requester_id=1,
            client_mutation_id="mutation-1",
        )
    )

    assert len(uow.events) == 1
    event = uow.events[0]
    assert isinstance(event, MemberRemoved)
    assert event.user_id == 2
    assert event.remaining_user_ids == [1]
    assert event.actor_user_id == 1
    assert event.project_id == 100
    assert event.client_mutation_id == "mutation-1"


@pytest.mark.asyncio
async def test_update_member_role_use_case_registers_role_changed_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = FakeUnitOfWork()
    monkeypatch.setattr("src.projects.use_cases.ProjectRepository", FakeProjectRepository)
    use_case = UpdateMemberRoleUseCase(lambda: uow)  # type: ignore[arg-type]

    result = await use_case.execute(
        UpdateMemberRoleCommand(
            project_id=100,
            user_id=2,
            role=ProjectRole.MANAGER,
            requester_id=1,
            client_mutation_id="mutation-1",
        )
    )

    assert result.role == ProjectRole.MANAGER
    assert len(uow.events) == 1
    event = uow.events[0]
    assert isinstance(event, MemberRoleChanged)
    assert event.user_id == 2
    assert event.role == ProjectRole.MANAGER
    assert event.previous_role == ProjectRole.MEMBER
    assert event.affected_user_ids == [1]
    assert event.actor_user_id == 1
    assert event.project_id == 100
    assert event.client_mutation_id == "mutation-1"
