from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from src.errors import SuccessCode
from src.invitations.dto import (
    AcceptInvitationCommand,
    CreateInvitationCommand,
    DeleteInvitationCommand,
)
from src.invitations.events import (
    InvitationAccepted,
    InvitationCreated,
    InvitationDeleted,
)
from src.invitations.repository import InvitationRepository
from src.invitations.use_cases import (
    AcceptInvitationUseCase,
    CreateInvitationUseCase,
    DeleteInvitationUseCase,
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


class FakeInvitationRepository:
    existing_member = False

    def __init__(self, session: object) -> None:
        self.inviter_member = SimpleNamespace(role=ProjectRole.OWNER)
        self.invitation = SimpleNamespace(
            id=10,
            token="token-1",
            project_id=100,
            inviter_id=1,
            role=ProjectRole.MEMBER,
            email=None,
            max_uses=1,
            used_count=0,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )

    async def get_project_member(self, *, project_id: int, user_id: int):
        if user_id == 1:
            return self.inviter_member
        if self.existing_member:
            return SimpleNamespace(role=ProjectRole.MEMBER)
        return None

    async def get_invitation(self, *, invitation_id: int, project_id: int):
        return self.invitation

    async def get_invitation_by_token_for_update(self, token: str):
        return self.invitation

    def add_invitation(self, invitation) -> None:
        self.invitation = invitation

    async def delete_invitation(self, invitation) -> None:
        self.deleted_invitation = invitation

    def save_invitation(self, invitation) -> None:
        self.invitation = invitation

    def add_member(self, member) -> None:
        self.new_member = member

    async def touch_project(self, project_id: int) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def get_project_member_user_ids(self, project_id: int):
        return [1, 2]


@pytest.mark.asyncio
async def test_invitation_repository_methods_do_not_commit() -> None:
    session = FakeSession()
    repository = InvitationRepository(session)  # type: ignore[arg-type]
    invitation = SimpleNamespace(id=1)

    repository.add_invitation(invitation)  # type: ignore[arg-type]
    repository.save_invitation(invitation)  # type: ignore[arg-type]
    await repository.delete_invitation(invitation)  # type: ignore[arg-type]
    await repository.touch_project(1)

    assert session.added == [invitation, invitation]
    assert session.deleted == [invitation]
    assert session.execute_count == 1
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_create_invitation_registers_invitation_created_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = FakeUnitOfWork()
    monkeypatch.setattr(
        "src.invitations.use_cases.InvitationRepository",
        FakeInvitationRepository,
    )
    use_case = CreateInvitationUseCase(lambda: uow, token_factory=lambda: "token-1")  # type: ignore[arg-type]

    invitation = await use_case.execute(
        CreateInvitationCommand(
            project_id=100,
            inviter_id=1,
            role=ProjectRole.MEMBER,
            email=None,
            max_uses=1,
            expires_in_days=7,
            client_mutation_id="mutation-1",
        )
    )

    assert invitation.token == "token-1"
    assert len(uow.events) == 1
    event = uow.events[0]
    assert isinstance(event, InvitationCreated)
    assert event.invitation is invitation
    assert event.actor_user_id == 1
    assert event.project_id == 100
    assert event.client_mutation_id == "mutation-1"


@pytest.mark.asyncio
async def test_delete_invitation_registers_invitation_deleted_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = FakeUnitOfWork()
    monkeypatch.setattr(
        "src.invitations.use_cases.InvitationRepository",
        FakeInvitationRepository,
    )
    use_case = DeleteInvitationUseCase(lambda: uow)  # type: ignore[arg-type]

    await use_case.execute(
        DeleteInvitationCommand(
            invitation_id=10,
            project_id=100,
            actor_user_id=1,
            client_mutation_id="mutation-1",
        )
    )

    assert len(uow.events) == 1
    event = uow.events[0]
    assert isinstance(event, InvitationDeleted)
    assert event.invitation_id == 10
    assert event.actor_user_id == 1
    assert event.project_id == 100
    assert event.client_mutation_id == "mutation-1"


@pytest.mark.asyncio
async def test_accept_invitation_registers_invitation_accepted_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = FakeUnitOfWork()
    FakeInvitationRepository.existing_member = False
    monkeypatch.setattr(
        "src.invitations.use_cases.InvitationRepository",
        FakeInvitationRepository,
    )
    use_case = AcceptInvitationUseCase(lambda: uow)  # type: ignore[arg-type]

    response = await use_case.execute(
        AcceptInvitationCommand(
            token="token-1",
            user_id=2,
            user_email="member@example.com",
            client_mutation_id="mutation-1",
        )
    )

    assert response.project_id == 100
    assert response.success.code == SuccessCode.INVITATION_ACCEPT_SUCCESS
    assert len(uow.events) == 1
    event = uow.events[0]
    assert isinstance(event, InvitationAccepted)
    assert event.user_id == 2
    assert event.role == ProjectRole.MEMBER
    assert event.affected_user_ids == [1, 2]
    assert event.actor_user_id == 2
    assert event.project_id == 100
    assert event.client_mutation_id == "mutation-1"


@pytest.mark.asyncio
async def test_accept_invitation_existing_member_returns_without_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = FakeUnitOfWork()
    FakeInvitationRepository.existing_member = True
    monkeypatch.setattr(
        "src.invitations.use_cases.InvitationRepository",
        FakeInvitationRepository,
    )
    use_case = AcceptInvitationUseCase(lambda: uow)  # type: ignore[arg-type]

    response = await use_case.execute(
        AcceptInvitationCommand(
            token="token-1",
            user_id=2,
            user_email="member@example.com",
        )
    )

    assert response.project_id == 100
    assert response.success.code == SuccessCode.ALREADY_PROJECT_MEMBER
    assert uow.events == []
