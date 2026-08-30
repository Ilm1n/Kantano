from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4

from fastapi.testclient import TestClient

from src.realtimev1.events import RealtimeEventType
from tests.registration_helpers import register_and_confirm

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


def _auth_headers(token: str, client_mutation_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if client_mutation_id:
        headers["X-Client-Mutation-Id"] = client_mutation_id
    return headers


def _create_project(client: TestClient, *, token: str, name: str) -> dict:
    response = client.post(
        "/api/projects/",
        json={"name": name, "description": None, "color": "#3B82F6"},
        headers=_auth_headers(token, str(uuid4())),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_column(
    client: TestClient,
    *,
    token: str,
    project_id: int,
    name: str = "Todo",
    tasks_limit: int | None = None,
    client_mutation_id: str | None = None,
):
    return client.post(
        f"/api/projects/{project_id}/columns",
        json={"name": name, "tasksLimit": tasks_limit},
        headers=_auth_headers(token, client_mutation_id or str(uuid4())),
    )


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


def test_owner_can_create_column_with_unchanged_response_shape(
    client: TestClient,
) -> None:
    owner = _register_and_login(
        client,
        username="owner_create_column",
        email="owner_create_column@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Columns")

    response = _create_column(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="Backlog",
        tasks_limit=7,
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["name"] == "Backlog"
    assert payload["tasksLimit"] == 7
    assert payload["projectId"] == project["id"]
    assert payload["position"] > 0
    assert payload["tasks"] == []


def test_member_cannot_create_column(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_member_column",
        email="owner_member_column@example.com",
    )
    member = _register_and_login(
        client,
        username="member_column",
        email="member_column@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Member Columns")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )

    response = _create_column(
        client,
        token=member["token"],
        project_id=project["id"],
        name="Nope",
    )

    assert response.status_code == 403
    _assert_error_code(response, "INSUFFICIENT_PERMISSIONS")


def test_manager_can_update_and_reorder_columns(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_update_column",
        email="owner_update_column@example.com",
    )
    manager = _register_and_login(
        client,
        username="manager_update_column",
        email="manager_update_column@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Manager Columns")
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
    first = _create_column(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="First",
    ).json()
    second = _create_column(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="Second",
    ).json()

    update_response = client.patch(
        f"/api/projects/{project['id']}/columns/{first['id']}",
        json={"name": "Updated", "tasksLimit": 3},
        headers=_auth_headers(manager["token"], str(uuid4())),
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["name"] == "Updated"
    assert update_response.json()["tasksLimit"] == 3

    reorder_response = client.post(
        f"/api/projects/{project['id']}/columns/reorder",
        json={"columnIds": [second["id"], first["id"]]},
        headers=_auth_headers(manager["token"], str(uuid4())),
    )
    assert reorder_response.status_code == 204, reorder_response.text

    board_response = client.get(
        f"/api/projects/{project['id']}/columns",
        headers=_auth_headers(owner["token"]),
    )
    assert board_response.status_code == 200, board_response.text
    assert [column["id"] for column in board_response.json()] == [
        second["id"],
        first["id"],
    ]


def test_delete_column_not_found(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_delete_missing_column",
        email="owner_delete_missing_column@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Delete Missing")

    response = client.delete(
        f"/api/projects/{project['id']}/columns/999999",
        headers=_auth_headers(owner["token"], str(uuid4())),
    )

    assert response.status_code == 404
    _assert_error_code(response, "COLUMN_NOT_FOUND")


def test_column_realtime_contracts(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_column_realtime",
        email="owner_column_realtime@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Realtime Columns")

    with _auth_project_ws(client, token=owner["token"], project_id=project["id"]) as ws:
        create_mutation_id = str(uuid4())
        create_response = _create_column(
            client,
            token=owner["token"],
            project_id=project["id"],
            name="Realtime",
            client_mutation_id=create_mutation_id,
        )
        assert create_response.status_code == 201, create_response.text
        created = create_response.json()
        create_event = _receive_event(ws, RealtimeEventType.COLUMN_CREATED)
        assert create_event["clientMutationId"] == create_mutation_id
        assert create_event["payload"]["column"]["id"] == created["id"]
        assert create_event["payload"]["column"]["name"] == "Realtime"

        update_mutation_id = str(uuid4())
        update_response = client.patch(
            f"/api/projects/{project['id']}/columns/{created['id']}",
            json={"name": "Renamed"},
            headers=_auth_headers(owner["token"], update_mutation_id),
        )
        assert update_response.status_code == 200, update_response.text
        update_event = _receive_event(ws, RealtimeEventType.COLUMN_UPDATED)
        assert update_event["clientMutationId"] == update_mutation_id
        assert update_event["payload"]["column"]["id"] == created["id"]
        assert update_event["payload"]["column"]["name"] == "Renamed"

        reorder_mutation_id = str(uuid4())
        reorder_response = client.post(
            f"/api/projects/{project['id']}/columns/reorder",
            json={"columnIds": [created["id"]]},
            headers=_auth_headers(owner["token"], reorder_mutation_id),
        )
        assert reorder_response.status_code == 204, reorder_response.text
        reorder_event = _receive_event(ws, RealtimeEventType.COLUMNS_REORDERED)
        assert reorder_event["clientMutationId"] == reorder_mutation_id
        assert reorder_event["payload"]["columnOrder"] == [created["id"]]

        delete_mutation_id = str(uuid4())
        delete_response = client.delete(
            f"/api/projects/{project['id']}/columns/{created['id']}",
            headers=_auth_headers(owner["token"], delete_mutation_id),
        )
        assert delete_response.status_code == 204, delete_response.text
        delete_event = _receive_event(ws, RealtimeEventType.COLUMN_DELETED)
        assert delete_event["clientMutationId"] == delete_mutation_id
        assert delete_event["payload"] == {"columnId": created["id"]}
