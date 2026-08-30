from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from src.main import main_app
from src.users.storage import AvatarStorageError, get_avatar_storage_gateway
from tests.registration_helpers import register_and_confirm

PASSWORD = "VeryStrongPass123!"
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01"
    b"\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FakeAvatarStorageGateway:
    def __init__(self) -> None:
        self.uploaded: list[str] = []
        self.deleted: list[str] = []
        self.fail_upload = False

    async def upload_file(
        self,
        *,
        file_data: bytes,
        object_name: str,
        content_type: str,
    ) -> str:
        if self.fail_upload:
            raise AvatarStorageError()
        self.uploaded.append(object_name)
        return f"http://storage.local/test/{object_name}"

    async def delete_file(self, object_name: str) -> None:
        self.deleted.append(object_name)

    def object_key_from_url(self, url: str | None) -> str | None:
        if not url:
            return None
        marker = "/test/"
        if marker not in url:
            return None
        return url.split(marker, 1)[1]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_and_login(
    client: TestClient,
    *,
    username: str,
    email: str,
) -> dict:
    suffix = uuid4().hex[:8]
    unique_username = f"{username}_{suffix}"
    local_part, _, domain = email.partition("@")
    unique_email = f"{local_part}+{suffix}@{domain}" if domain else f"{email}_{suffix}"

    register_and_confirm(
        client,
        username=unique_username,
        email=unique_email,
        password=PASSWORD,
    )

    login_resp = client.post(
        "/api/auth/login",
        data={"username": unique_username, "password": PASSWORD},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["accessToken"]

    me_resp = client.get(
        "/api/users/me",
        headers=_auth_headers(token),
    )
    assert me_resp.status_code == 200, me_resp.text
    return {"token": token, "user": me_resp.json()}


def _upload_avatar(client: TestClient, *, token: str):
    return client.post(
        "/api/users/me/avatar",
        files={"file": ("avatar.png", PNG_BYTES, "image/png")},
        headers=_auth_headers(token),
    )


def _assert_error_code(response, expected_code: str) -> None:
    assert response.json() == {"error": {"code": expected_code}}


def test_upload_replace_and_delete_avatar_with_storage_cleanup(
    client: TestClient,
) -> None:
    storage = FakeAvatarStorageGateway()
    main_app.dependency_overrides[get_avatar_storage_gateway] = lambda: storage
    try:
        user = _register_and_login(
            client,
            username="avatar_user",
            email="avatar_user@example.com",
        )

        first_upload = _upload_avatar(client, token=user["token"])
        assert first_upload.status_code == 200, first_upload.text
        first_avatar = first_upload.json()["avatarUrl"]
        assert first_avatar.endswith(storage.uploaded[0])
        assert storage.deleted == []

        second_upload = _upload_avatar(client, token=user["token"])
        assert second_upload.status_code == 200, second_upload.text
        second_avatar = second_upload.json()["avatarUrl"]
        assert second_avatar.endswith(storage.uploaded[1])
        assert storage.deleted == [storage.uploaded[0]]

        delete_response = client.delete(
            "/api/users/me/avatar",
            headers=_auth_headers(user["token"]),
        )
        assert delete_response.status_code == 200, delete_response.text
        assert delete_response.json()["avatarUrl"] is None
        assert storage.deleted == [storage.uploaded[0], storage.uploaded[1]]
    finally:
        main_app.dependency_overrides.pop(get_avatar_storage_gateway, None)


def test_avatar_upload_failure_returns_file_upload_failed(client: TestClient) -> None:
    storage = FakeAvatarStorageGateway()
    storage.fail_upload = True
    main_app.dependency_overrides[get_avatar_storage_gateway] = lambda: storage
    try:
        user = _register_and_login(
            client,
            username="avatar_fail_user",
            email="avatar_fail_user@example.com",
        )

        response = _upload_avatar(client, token=user["token"])

        assert response.status_code == 503
        _assert_error_code(response, "FILE_UPLOAD_FAILED")
    finally:
        main_app.dependency_overrides.pop(get_avatar_storage_gateway, None)
