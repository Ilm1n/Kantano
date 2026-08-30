from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.errors import ErrorCode
from src.shared.errors import DatabaseError
from src.users.dto import (
    UpdateUserCommand,
    UpdateUserPasswordCommand,
    UploadAvatarCommand,
)
from src.users.repository import UserRepository
from src.users.storage import LocalAvatarStorageGateway
from src.users.use_cases import (
    UpdateUserPasswordUseCase,
    UpdateUserUseCase,
    UploadAvatarUseCase,
)


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commit_count = 0
        self.flush_count = 0
        self.refresh_count = 0

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def get(self, model, ident: int):
        return None

    async def commit(self) -> None:
        self.commit_count += 1

    async def flush(self) -> None:
        self.flush_count += 1

    async def refresh(self, instance: object) -> None:
        self.refresh_count += 1


class FakeUnitOfWork:
    def __init__(self, *, fail_commit: bool = False) -> None:
        self.session = object()
        self.fail_commit = fail_commit
        self.commit_count = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        return False

    async def commit(self) -> None:
        self.commit_count += 1
        if self.fail_commit:
            raise RuntimeError("commit failed")


class FakeUserRepository:
    def __init__(self, session: object) -> None:
        self.user = SimpleNamespace(
            id=1,
            username="user",
            email="user@example.com",
            hashed_password=None,
            full_name=None,
            avatar_url=None,
            is_active=True,
        )

    def add_user(self, **kwargs):
        self.user.username = kwargs["username"]
        self.user.email = kwargs["email"]
        self.user.hashed_password = kwargs["hashed_password"]
        return self.user

    async def get_user(self, user_id: int):
        self.user.id = user_id
        return self.user

    def save_user(self, user: object) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def refresh_user(self, user: object) -> None:
        return None


class FakeAvatarStorage:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def upload_file(self, *, file_data: bytes, object_name: str, content_type: str):
        return f"http://storage.local/test/{object_name}"

    async def delete_file(self, object_name: str) -> None:
        self.deleted.append(object_name)

    def object_key_from_url(self, url: str | None) -> str | None:
        return None


@pytest.mark.asyncio
async def test_user_repository_methods_do_not_commit() -> None:
    session = FakeSession()
    repository = UserRepository(session)  # type: ignore[arg-type]
    user = SimpleNamespace(id=1)

    repository.add_user(
        email="user@example.com",
        username="user",
        hashed_password="hash",
    )
    repository.save_user(user)  # type: ignore[arg-type]
    await repository.flush()
    await repository.refresh_user(user)  # type: ignore[arg-type]

    assert session.added
    assert session.flush_count == 1
    assert session.refresh_count == 1
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_update_user_use_case_applies_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = FakeUnitOfWork()
    monkeypatch.setattr("src.users.use_cases.UserRepository", FakeUserRepository)
    use_case = UpdateUserUseCase(lambda: uow)  # type: ignore[arg-type]

    result = await use_case.execute(
        UpdateUserCommand(
            user_id=1,
            changes={"username": "renamed", "full_name": "Ada"},
        )
    )

    assert result.username == "renamed"
    assert result.full_name == "Ada"


@pytest.mark.asyncio
async def test_update_password_use_case_hashes_new_password_for_passwordless_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = FakeUnitOfWork()
    monkeypatch.setattr("src.users.use_cases.UserRepository", FakeUserRepository)
    monkeypatch.setattr("src.users.use_cases.hash_password", lambda value: f"hashed:{value}")
    use_case = UpdateUserPasswordUseCase(lambda: uow)  # type: ignore[arg-type]

    result = await use_case.execute(
        UpdateUserPasswordCommand(
            user_id=1,
            current_password=None,
            new_password="new-password",
        )
    )

    assert result.hashed_password == "hashed:new-password"


@pytest.mark.asyncio
async def test_upload_avatar_use_case_deletes_new_object_on_commit_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = FakeUnitOfWork(fail_commit=True)
    storage = FakeAvatarStorage()
    monkeypatch.setattr("src.users.use_cases.UserRepository", FakeUserRepository)
    use_case = UploadAvatarUseCase(
        lambda: uow,  # type: ignore[arg-type]
        storage,  # type: ignore[arg-type]
        object_name_factory=lambda user_id, extension: f"avatars/user_{user_id}.{extension}",
    )

    with pytest.raises(DatabaseError) as exc_info:
        await use_case.execute(
            UploadAvatarCommand(
                user_id=1,
                file_data=b"image",
                extension="png",
                mime_type="image/png",
            )
        )

    assert exc_info.value.code == ErrorCode.DB_COMMIT_FAILED
    assert storage.deleted == ["avatars/user_1.png"]


@pytest.mark.asyncio
async def test_local_avatar_storage_upload_extracts_key_and_deletes(
    tmp_path: Path,
) -> None:
    storage = LocalAvatarStorageGateway(
        storage_dir=tmp_path,
        public_base_url="http://localhost:8000/local-storage",
    )

    url = await storage.upload_file(
        file_data=b"image",
        object_name="avatars/user_1.png",
        content_type="image/png",
    )

    object_path = tmp_path / "avatars" / "user_1.png"
    assert url == "http://localhost:8000/local-storage/avatars/user_1.png"
    assert object_path.read_bytes() == b"image"
    assert storage.object_key_from_url(url) == "avatars/user_1.png"

    await storage.delete_file("avatars/user_1.png")

    assert not object_path.exists()
