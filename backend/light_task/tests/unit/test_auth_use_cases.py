from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.auth.dto import LoginCommand, RefreshTokenCommand
from src.auth.repository import AuthRepository
from src.auth.use_cases import LoginUseCase, RefreshTokenUseCase
from src.errors import ErrorCode
from src.shared.errors import UnauthorizedError


class FakeExecuteResult:
    def scalar_one_or_none(self):
        return None


class FakeSession:
    def __init__(self) -> None:
        self.execute_count = 0
        self.commit_count = 0

    async def execute(self, statement):
        self.execute_count += 1
        return FakeExecuteResult()

    async def get(self, model, ident: int):
        return None

    async def commit(self) -> None:
        self.commit_count += 1


class FakeSessionContext:
    def __init__(self, session: object) -> None:
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        return False


class FakeAuthRepository:
    def __init__(self, session: object) -> None:
        self.user = SimpleNamespace(
            id=1,
            username="user",
            email="user@example.com",
            hashed_password="hashed",
            is_active=True,
        )

    async def get_user_by_username_or_email(self, username_or_email: str):
        return self.user

    async def get_user(self, user_id: int):
        self.user.id = user_id
        return self.user


@pytest.mark.asyncio
async def test_auth_repository_methods_do_not_commit() -> None:
    session = FakeSession()
    repository = AuthRepository(session)  # type: ignore[arg-type]

    await repository.get_user_by_username_or_email("user")
    await repository.get_user(1)

    assert session.execute_count == 1
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_login_use_case_returns_token_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.auth.use_cases.AuthRepository", FakeAuthRepository)
    monkeypatch.setattr("src.auth.use_cases.validate_password", lambda raw, hashed: True)
    monkeypatch.setattr(
        "src.auth.use_cases.create_token_result",
        lambda user: SimpleNamespace(
            access_token="access",
            refresh_token="refresh",
            token_type="bearer",
        ),
    )
    use_case = LoginUseCase(lambda: FakeSessionContext(object()))  # type: ignore[arg-type]

    result = await use_case.execute(LoginCommand(username_or_email="user", password="password"))

    assert result.access_token == "access"
    assert result.refresh_token == "refresh"
    assert result.token_type == "bearer"


@pytest.mark.asyncio
async def test_refresh_use_case_rejects_missing_refresh_token() -> None:
    use_case = RefreshTokenUseCase(lambda: FakeSessionContext(object()))  # type: ignore[arg-type]

    with pytest.raises(UnauthorizedError) as exc_info:
        await use_case.execute(RefreshTokenCommand(refresh_token=None))

    assert exc_info.value.code == ErrorCode.REFRESH_TOKEN_MISSING
