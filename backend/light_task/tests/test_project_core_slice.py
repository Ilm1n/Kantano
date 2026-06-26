from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4

from fastapi.testclient import TestClient

from src.realtimev1.events import RealtimeEventType

PASSWORD = "VeryStrongPass123!"


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

    register_resp = client.post(
        "/api/users/register",
        json={
            "username": unique_username,
            "email": unique_email,
            "password": PASSWORD,
        },
    )
    assert register_resp.status_code == 201, register_resp.text

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


def _auth_headers(token: str, client_mutation_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if client_mutation_id:
        headers["X-Client-Mutation-Id"] = client_mutation_id
    return headers


def _create_project(
    client: TestClient,
    *,
    token: str,
    name: str,
    client_mutation_id: str | None = None,
) -> dict:
    response = client.post(
        "/api/projects/",
        json={"name": name, "description": None, "color": "#3B82F6"},
        headers=_auth_headers(token, client_mutation_id or str(uuid4())),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _add_member_via_invite(
    client: TestClient,
    *,
    owner_token: str,
    member_token: str,
    project_id: int,
) -> None:
    invite_resp = client.post(
        f"/api/projects/{project_id}/invite",
        json={"role": "MEMBER", "email": None, "maxUses": 1, "expiresInDays": 7},
        headers=_auth_headers(owner_token, str(uuid4())),
    )
    assert invite_resp.status_code == 201, invite_resp.text

    accept_resp = client.post(
        f"/api/invitations/{invite_resp.json()['token']}/accept",
        headers=_auth_headers(member_token, str(uuid4())),
    )
    assert accept_resp.status_code == 200, accept_resp.text


def _promote_member_to_manager(
    client: TestClient,
    *,
    owner_token: str,
    project_id: int,
    user_id: int,
) -> None:
    response = client.patch(
        f"/api/projects/{project_id}/members/{user_id}",
        json={"role": "MANAGER"},
        headers=_auth_headers(owner_token, str(uuid4())),
    )
    assert response.status_code == 200, response.text


@contextmanager
def _auth_user_ws(client: TestClient, *, token: str):
    with client.websocket_connect("/ws/user") as ws:
        ws.send_json({"type": "auth", "accessToken": token})
        ws.send_json({"type": "ping"})
        _receive_pong(ws)
        yield ws


@contextmanager
def _auth_project_ws(client: TestClient, *, token: str, project_id: int):
    with client.websocket_connect(f"/ws/projects/{project_id}") as ws:
        ws.send_json({"type": "auth", "accessToken": token})
        assert ws.receive_json()["eventType"] == RealtimeEventType.PROJECT_PRESENCE_SYNC
        assert ws.receive_json()["eventType"] == RealtimeEventType.TASK_PRESENCE_SYNC
        ws.send_json({"type": "ping"})
        _receive_pong(ws)
        yield ws


def _receive_event(ws, event_type: str, max_messages: int = 20) -> dict:
    for _ in range(max_messages):
        message = ws.receive_json()
        if message.get("eventType") == event_type:
            return message
    raise AssertionError(f"Event {event_type} was not received")


def _receive_pong(ws, max_messages: int = 10) -> None:
    for _ in range(max_messages):
        message = ws.receive_json()
        if message.get("type") == "pong":
            return
    raise AssertionError("Pong was not received from websocket")


def _assert_error_code(response, expected_code: str) -> None:
    assert response.json() == {"error": {"code": expected_code}}


def test_create_project_response_shape_and_default_tags(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_create_project_core",
        email="owner_create_project_core@example.com",
    )

    project = _create_project(client, token=owner["token"], name="Core Project")

    assert project["name"] == "Core Project"
    assert project["ownerId"] == owner["user"]["id"]
    assert project["currentUserRole"] == "OWNER"

    tags_response = client.get(
        f"/api/projects/{project['id']}/tags",
        headers=_auth_headers(owner["token"]),
    )
    assert tags_response.status_code == 200, tags_response.text
    assert len(tags_response.json()) > 0


def test_manager_cannot_update_or_delete_project(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_project_manager_denied",
        email="owner_project_manager_denied@example.com",
    )
    manager = _register_and_login(
        client,
        username="manager_project_denied",
        email="manager_project_denied@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Manager Denied")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=manager["token"],
        project_id=project["id"],
    )
    _promote_member_to_manager(
        client,
        owner_token=owner["token"],
        project_id=project["id"],
        user_id=manager["user"]["id"],
    )

    update_response = client.patch(
        f"/api/projects/{project['id']}",
        json={"name": "Denied"},
        headers=_auth_headers(manager["token"], str(uuid4())),
    )
    assert update_response.status_code == 403
    _assert_error_code(update_response, "INSUFFICIENT_PERMISSIONS")

    delete_response = client.delete(
        f"/api/projects/{project['id']}",
        headers=_auth_headers(manager["token"], str(uuid4())),
    )
    assert delete_response.status_code == 403
    _assert_error_code(delete_response, "INSUFFICIENT_PERMISSIONS")


def test_project_update_and_delete_realtime_contracts(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_project_realtime_core",
        email="owner_project_realtime_core@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Realtime Core")

    with _auth_user_ws(client, token=owner["token"]) as user_ws:
        with _auth_project_ws(
            client,
            token=owner["token"],
            project_id=project["id"],
        ) as project_ws:
            update_mutation_id = str(uuid4())
            update_response = client.patch(
                f"/api/projects/{project['id']}",
                json={"name": "Renamed Core", "color": "#10B981"},
                headers=_auth_headers(owner["token"], update_mutation_id),
            )
            assert update_response.status_code == 200, update_response.text
            update_event = _receive_event(project_ws, RealtimeEventType.PROJECT_UPDATED)
            assert update_event["clientMutationId"] == update_mutation_id
            assert update_event["payload"]["project"]["id"] == project["id"]
            assert update_event["payload"]["project"]["name"] == "Renamed Core"
            list_event = _receive_event(
                user_ws,
                RealtimeEventType.PROJECT_LIST_ITEM_UPDATED,
            )
            assert list_event["payload"]["reason"] == str(RealtimeEventType.PROJECT_UPDATED)

            delete_mutation_id = str(uuid4())
            delete_response = client.delete(
                f"/api/projects/{project['id']}",
                headers=_auth_headers(owner["token"], delete_mutation_id),
            )
            assert delete_response.status_code == 204, delete_response.text
            delete_event = _receive_event(project_ws, RealtimeEventType.PROJECT_DELETED)
            assert delete_event["clientMutationId"] == delete_mutation_id
            assert delete_event["payload"] == {"projectId": project["id"]}
            removed_event = _receive_event(
                user_ws,
                RealtimeEventType.PROJECT_REMOVED_FROM_USER,
            )
            assert removed_event["clientMutationId"] == delete_mutation_id
            assert removed_event["payload"] == {"projectId": project["id"]}


def test_project_create_realtime_contract(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_project_create_realtime",
        email="owner_project_create_realtime@example.com",
    )

    with _auth_user_ws(client, token=owner["token"]) as user_ws:
        mutation_id = str(uuid4())
        project = _create_project(
            client,
            token=owner["token"],
            name="Created Realtime",
            client_mutation_id=mutation_id,
        )
        added_event = _receive_event(user_ws, RealtimeEventType.PROJECT_ADDED_TO_USER)
        assert added_event["clientMutationId"] == mutation_id
        assert added_event["payload"]["project"]["id"] == project["id"]
        assert added_event["payload"]["project"]["currentUserRole"] == "OWNER"
