from __future__ import annotations

import asyncio
import time
from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.config import settings
from src.realtimev1.events import (
    SYSTEM_ACTOR_USER_ID,
    RealtimeDeliveryMessage,
    RealtimeEventType,
    RealtimeScope,
    new_event_envelope,
)
from src.realtimev1.redis_event_bus import RedisEventBus

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
        data={
            "username": unique_username,
            "password": PASSWORD,
        },
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["accessToken"]

    me_resp = client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200, me_resp.text
    user = me_resp.json()
    return {"token": token, "user": user}


def _auth_headers(token: str, client_mutation_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if client_mutation_id:
        headers["X-Client-Mutation-Id"] = client_mutation_id
    return headers


def _create_project(client: TestClient, *, token: str, name: str = "Test Project") -> dict:
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
    name: str,
) -> dict:
    response = client.post(
        f"/api/projects/{project_id}/columns",
        json={"name": name, "tasksLimit": None},
        headers=_auth_headers(token, str(uuid4())),
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
    token = invite_resp.json()["token"]

    accept_resp = client.post(
        f"/api/invitations/{token}/accept",
        headers=_auth_headers(member_token, str(uuid4())),
    )
    assert accept_resp.status_code == 200, accept_resp.text


@contextmanager
def _auth_user_ws(client: TestClient, *, token: str):
    with client.websocket_connect("/ws/user") as ws:
        ws.send_json({"type": "auth", "accessToken": token})
        ws.send_json({"type": "ping"})
        pong = ws.receive_json()
        assert pong["type"] == "pong"
        yield ws


@contextmanager
def _auth_project_ws(client: TestClient, *, token: str, project_id: int):
    with client.websocket_connect(f"/ws/projects/{project_id}") as ws:
        ws.send_json({"type": "auth", "accessToken": token})
        # Initial project and task presence syncs are sent right after auth.
        project_presence_sync = ws.receive_json()
        assert project_presence_sync["eventType"] == RealtimeEventType.PROJECT_PRESENCE_SYNC
        task_presence_sync = ws.receive_json()
        assert task_presence_sync["eventType"] == RealtimeEventType.TASK_PRESENCE_SYNC
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


def _receive_until_pong_without_invitation(ws, max_messages: int = 10) -> None:
    ws.send_json({"type": "ping"})
    for _ in range(max_messages):
        message = ws.receive_json()
        if message.get("eventType") == RealtimeEventType.INVITATION_CREATED:
            raise AssertionError("Regular member received manager-only invitation event")
        if message.get("type") == "pong":
            return
    raise AssertionError("Pong was not received from websocket")


def _assert_project_presence_event(message: dict, *, expected_count: int) -> None:
    assert message["eventType"] == "project.presence.sync"
    assert message["payload"]["projectId"] == message["projectId"]
    assert message["payload"]["activeUserCount"] == expected_count


def _expect_disconnect(ws, max_messages: int = 20) -> None:
    for _ in range(max_messages):
        try:
            ws.receive_json()
        except WebSocketDisconnect:
            return
    raise AssertionError("Websocket was expected to be closed, but remained open")


def test_websocket_auth_happy_path(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_auth",
        email="owner_auth@example.com",
    )
    with _auth_user_ws(client, token=owner["token"]):
        pass


def test_websocket_auth_reject_invalid_token(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/user") as ws:
            ws.send_json({"type": "auth", "accessToken": "invalid-token"})
            ws.receive_json()


def test_project_subscription_permission(client: TestClient) -> None:
    owner = _register_and_login(client, username="owner_perm", email="owner_perm@example.com")
    member = _register_and_login(client, username="member_perm", email="member_perm@example.com")
    outsider = _register_and_login(
        client,
        username="outsider_perm",
        email="outsider_perm@example.com",
    )

    project = _create_project(client, token=owner["token"], name="Permission Project")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )

    with _auth_project_ws(client, token=member["token"], project_id=project["id"]):
        pass

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/projects/{project['id']}") as ws:
            ws.send_json({"type": "auth", "accessToken": outsider["token"]})
            ws.receive_json()


def test_project_presence_count_lifecycle(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_project_presence",
        email="owner_project_presence@example.com",
    )
    member = _register_and_login(
        client,
        username="member_project_presence",
        email="member_project_presence@example.com",
    )
    outsider = _register_and_login(
        client,
        username="outsider_project_presence",
        email="outsider_project_presence@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Project Presence")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )

    with client.websocket_connect(f"/ws/projects/{project['id']}") as ws_owner:
        ws_owner.send_json({"type": "auth", "accessToken": owner["token"]})
        _assert_project_presence_event(ws_owner.receive_json(), expected_count=1)
        assert ws_owner.receive_json()["eventType"] == RealtimeEventType.TASK_PRESENCE_SYNC

        with client.websocket_connect(f"/ws/projects/{project['id']}") as ws_member:
            ws_member.send_json({"type": "auth", "accessToken": member["token"]})
            _assert_project_presence_event(ws_member.receive_json(), expected_count=2)
            assert ws_member.receive_json()["eventType"] == RealtimeEventType.TASK_PRESENCE_SYNC
            changed = _receive_event(ws_owner, "project.presence.changed")
            assert changed["payload"]["activeUserCount"] == 2

            with client.websocket_connect(f"/ws/projects/{project['id']}") as ws_member_second_tab:
                ws_member_second_tab.send_json({"type": "auth", "accessToken": member["token"]})
                _assert_project_presence_event(
                    ws_member_second_tab.receive_json(),
                    expected_count=2,
                )
                assert (
                    ws_member_second_tab.receive_json()["eventType"]
                    == RealtimeEventType.TASK_PRESENCE_SYNC
                )
                changed_same_user = _receive_event(ws_owner, "project.presence.changed")
                assert changed_same_user["payload"]["activeUserCount"] == 2

            changed_after_tab_close = _receive_event(ws_owner, "project.presence.changed")
            assert changed_after_tab_close["payload"]["activeUserCount"] == 2

            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(f"/ws/projects/{project['id']}") as ws_outsider:
                    ws_outsider.send_json({"type": "auth", "accessToken": outsider["token"]})
                    ws_outsider.receive_json()

        changed_after_member_close = _receive_event(ws_owner, "project.presence.changed")
        assert changed_after_member_close["payload"]["activeUserCount"] == 1


def test_task_created_event_delivery(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_task_create",
        email="owner_task_create@example.com",
    )
    member = _register_and_login(
        client,
        username="member_task_create",
        email="member_task_create@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Task Created Events")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )
    column = _create_column(
        client,
        token=owner["token"],
        project_id=project["id"],
        name="Todo",
    )

    with _auth_project_ws(client, token=member["token"], project_id=project["id"]) as ws_member:
        mutation_id = f"task-create-{uuid4()}"
        create_task_resp = client.post(
            f"/api/projects/{project['id']}/columns/{column['id']}/tasks",
            json={
                "title": "Realtime Task",
                "description": "created via api",
                "priority": "MEDIUM",
                "assigneeId": None,
                "tagIds": [],
            },
            headers=_auth_headers(owner["token"], mutation_id),
        )
        assert create_task_resp.status_code == 201, create_task_resp.text

        event = _receive_event(ws_member, RealtimeEventType.TASK_CREATED)
        assert event["payload"]["task"]["title"] == "Realtime Task"
        assert event["clientMutationId"] == mutation_id


def test_task_moved_event_delivery(client: TestClient) -> None:
    owner = _register_and_login(
        client, username="owner_task_move", email="owner_task_move@example.com"
    )
    member = _register_and_login(
        client, username="member_task_move", email="member_task_move@example.com"
    )
    project = _create_project(client, token=owner["token"], name="Task Move Events")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )
    column_a = _create_column(client, token=owner["token"], project_id=project["id"], name="A")
    column_b = _create_column(client, token=owner["token"], project_id=project["id"], name="B")

    task_resp = client.post(
        f"/api/projects/{project['id']}/columns/{column_a['id']}/tasks",
        json={
            "title": "Move me",
            "description": None,
            "priority": "MEDIUM",
            "assigneeId": None,
            "tagIds": [],
        },
        headers=_auth_headers(owner["token"], str(uuid4())),
    )
    assert task_resp.status_code == 201, task_resp.text
    task = task_resp.json()

    with _auth_project_ws(client, token=member["token"], project_id=project["id"]) as ws_member:
        mutation_id = f"task-move-{uuid4()}"
        move_resp = client.patch(
            f"/api/tasks/{task['id']}/move",
            json={"newColumnId": column_b["id"], "afterTaskId": None},
            headers=_auth_headers(owner["token"], mutation_id),
        )
        assert move_resp.status_code == 200, move_resp.text

        event = _receive_event(ws_member, RealtimeEventType.TASK_MOVED)
        assert event["payload"]["fromColumnId"] == column_a["id"]
        assert event["payload"]["toColumnId"] == column_b["id"]
        assert event["clientMutationId"] == mutation_id


def test_project_updated_emits_user_scope_list_update(client: TestClient) -> None:
    owner = _register_and_login(
        client, username="owner_project_update", email="owner_project_update@example.com"
    )
    member = _register_and_login(
        client, username="member_project_update", email="member_project_update@example.com"
    )
    project = _create_project(client, token=owner["token"], name="User Scope Events")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )

    with _auth_user_ws(client, token=member["token"]) as ws_user:
        mutation_id = f"project-update-{uuid4()}"
        patch_resp = client.patch(
            f"/api/projects/{project['id']}",
            json={"name": "Renamed Project"},
            headers=_auth_headers(owner["token"], mutation_id),
        )
        assert patch_resp.status_code == 200, patch_resp.text

        event = _receive_event(ws_user, RealtimeEventType.PROJECT_LIST_ITEM_UPDATED)
        assert event["payload"]["projectId"] == project["id"]
        assert event["clientMutationId"] == mutation_id


def test_member_removed_flow(client: TestClient) -> None:
    owner = _register_and_login(
        client, username="owner_member_removed", email="owner_member_removed@example.com"
    )
    member = _register_and_login(
        client, username="member_member_removed", email="member_member_removed@example.com"
    )
    project = _create_project(client, token=owner["token"], name="Member Removed Events")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )

    with _auth_user_ws(client, token=member["token"]) as ws_user:
        with _auth_project_ws(
            client, token=member["token"], project_id=project["id"]
        ) as ws_project:
            remove_resp = client.delete(
                f"/api/projects/{project['id']}/members/{member['user']['id']}",
                headers=_auth_headers(owner["token"], str(uuid4())),
            )
            assert remove_resp.status_code == 204, remove_resp.text

            user_event = _receive_event(ws_user, RealtimeEventType.PROJECT_REMOVED_FROM_USER)
            assert user_event["payload"]["projectId"] == project["id"]
            _expect_disconnect(ws_project)


def test_invitation_event_is_manager_only(client: TestClient) -> None:
    owner = _register_and_login(client, username="owner_inv", email="owner_inv@example.com")
    manager = _register_and_login(client, username="manager_inv", email="manager_inv@example.com")
    member = _register_and_login(client, username="member_inv", email="member_inv@example.com")
    project = _create_project(client, token=owner["token"], name="Invitation Audience")

    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=manager["token"],
        project_id=project["id"],
    )
    role_resp = client.patch(
        f"/api/projects/{project['id']}/members/{manager['user']['id']}",
        json={"role": "MANAGER"},
        headers=_auth_headers(owner["token"], str(uuid4())),
    )
    assert role_resp.status_code == 200, role_resp.text

    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )

    with _auth_project_ws(client, token=manager["token"], project_id=project["id"]) as ws_manager:
        with _auth_project_ws(client, token=member["token"], project_id=project["id"]) as ws_member:
            invite_resp = client.post(
                f"/api/projects/{project['id']}/invite",
                json={"role": "MEMBER", "email": None, "maxUses": 1, "expiresInDays": 7},
                headers=_auth_headers(owner["token"], str(uuid4())),
            )
            assert invite_resp.status_code == 201, invite_resp.text

            manager_event = _receive_event(ws_manager, RealtimeEventType.INVITATION_CREATED)
            assert manager_event["eventType"] == RealtimeEventType.INVITATION_CREATED

            _receive_until_pong_without_invitation(ws_member)


def test_presence_lifecycle_and_ttl_cleanup(client: TestClient) -> None:
    owner = _register_and_login(
        client, username="owner_presence", email="owner_presence@example.com"
    )
    member = _register_and_login(
        client, username="member_presence", email="member_presence@example.com"
    )
    project = _create_project(client, token=owner["token"], name="Presence Flow")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )
    column = _create_column(client, token=owner["token"], project_id=project["id"], name="Presence")
    task_resp = client.post(
        f"/api/projects/{project['id']}/columns/{column['id']}/tasks",
        json={
            "title": "Presence task",
            "description": None,
            "priority": "MEDIUM",
            "assigneeId": None,
            "tagIds": [],
        },
        headers=_auth_headers(owner["token"], str(uuid4())),
    )
    assert task_resp.status_code == 201, task_resp.text
    task = task_resp.json()

    with _auth_project_ws(client, token=owner["token"], project_id=project["id"]) as ws_owner:
        with _auth_project_ws(client, token=member["token"], project_id=project["id"]) as ws_member:
            ws_owner.send_json(
                {
                    "type": RealtimeEventType.TASK_VIEWING_STARTED,
                    "taskId": task["id"],
                }
            )
            started = _receive_event(ws_member, RealtimeEventType.TASK_VIEWING_STARTED)
            assert started["payload"]["taskId"] == task["id"]

            ws_owner.send_json(
                {
                    "type": RealtimeEventType.TASK_VIEWING_STOPPED,
                    "taskId": task["id"],
                }
            )
            stopped = _receive_event(ws_member, RealtimeEventType.TASK_VIEWING_STOPPED)
            assert stopped["payload"]["taskId"] == task["id"]

            ws_owner.send_json(
                {
                    "type": RealtimeEventType.TASK_EDITING_STARTED,
                    "taskId": task["id"],
                }
            )
            _receive_event(ws_member, RealtimeEventType.TASK_EDITING_STARTED)

            deadline = time.time() + 8
            stale_cleared = False
            while time.time() < deadline:
                message = ws_member.receive_json()
                if message.get("eventType") != RealtimeEventType.TASK_PRESENCE_SYNC:
                    continue
                items = message["payload"]["items"]
                task_item = next((item for item in items if item["taskId"] == task["id"]), None)
                editing_ids = task_item["editingUserIds"] if task_item else []
                if owner["user"]["id"] not in editing_ids:
                    stale_cleared = True
                    break

            assert stale_cleared, "Presence TTL cleanup did not clear stale editing presence"


def test_presence_event_fallback_to_local_delivery_on_redis_publish_failure(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = _register_and_login(
        client, username="owner_presence_fallback", email="owner_presence_fallback@example.com"
    )
    member = _register_and_login(
        client, username="member_presence_fallback", email="member_presence_fallback@example.com"
    )
    project = _create_project(client, token=owner["token"], name="Presence Fallback")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )
    column = _create_column(client, token=owner["token"], project_id=project["id"], name="Presence")
    task_resp = client.post(
        f"/api/projects/{project['id']}/columns/{column['id']}/tasks",
        json={
            "title": "Presence fallback task",
            "description": None,
            "priority": "MEDIUM",
            "assigneeId": None,
            "tagIds": [],
        },
        headers=_auth_headers(owner["token"], str(uuid4())),
    )
    assert task_resp.status_code == 201, task_resp.text
    task = task_resp.json()

    runtime = client.app.state.realtime_runtime

    async def broken_publish(_message: RealtimeDeliveryMessage) -> None:
        raise RuntimeError("redis unavailable for test")

    monkeypatch.setattr(runtime._event_bus, "publish", broken_publish)

    with _auth_project_ws(client, token=owner["token"], project_id=project["id"]) as ws_owner:
        with _auth_project_ws(client, token=member["token"], project_id=project["id"]) as ws_member:
            ws_owner.send_json(
                {
                    "type": RealtimeEventType.TASK_VIEWING_STARTED,
                    "taskId": task["id"],
                }
            )
            event = _receive_event(ws_member, RealtimeEventType.TASK_VIEWING_STARTED)
            assert event["payload"]["taskId"] == task["id"]
            assert event["payload"]["userId"] == owner["user"]["id"]


@pytest.mark.asyncio
async def test_redis_event_bus_fanout_between_two_subscribers(redis_client) -> None:
    channel = f"realtime.v1.tests.{uuid4()}"
    bus_first = RedisEventBus(redis_url=settings.realtime.redis_url, channel=channel)
    bus_second = RedisEventBus(redis_url=settings.realtime.redis_url, channel=channel)
    received_first: asyncio.Queue[RealtimeDeliveryMessage] = asyncio.Queue()
    received_second: asyncio.Queue[RealtimeDeliveryMessage] = asyncio.Queue()

    async def consume_first(message: RealtimeDeliveryMessage) -> None:
        await received_first.put(message)

    async def consume_second(message: RealtimeDeliveryMessage) -> None:
        await received_second.put(message)

    try:
        await bus_first.start(consume_first)
        await bus_second.start(consume_second)

        envelope = new_event_envelope(
            event_type=RealtimeEventType.PROJECT_UPDATED,
            scope=RealtimeScope.PROJECT,
            project_id=4242,
            actor_user_id=SYSTEM_ACTOR_USER_ID,
            payload={"projectId": 4242},
        )
        delivery = RealtimeDeliveryMessage(
            envelope=envelope,
            project_id=4242,
        )
        await bus_first.publish(delivery)

        first_delivery = await asyncio.wait_for(received_first.get(), timeout=3)
        second_delivery = await asyncio.wait_for(received_second.get(), timeout=3)
        assert first_delivery.envelope.event_id == envelope.event_id
        assert second_delivery.envelope.event_id == envelope.event_id
        assert second_delivery.project_id == 4242
    finally:
        await bus_first.stop()
        await bus_second.stop()
