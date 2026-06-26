from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from test_create_task_slice import (
    _add_member_via_invite,
    _auth_headers,
    _create_project,
    _promote_member_to_manager,
    _register_and_login,
)
from test_realtime_integration import (
    _auth_project_ws,
    _auth_user_ws,
    _receive_event,
)

from src.realtimev1.events import RealtimeEventType


def _create_invitation(
    client: TestClient,
    *,
    token: str,
    project_id: int,
    role: str = "MEMBER",
    email: str | None = None,
    max_uses: int | None = 1,
    client_mutation_id: str | None = None,
):
    return client.post(
        f"/api/projects/{project_id}/invite",
        json={
            "role": role,
            "email": email,
            "maxUses": max_uses,
            "expiresInDays": 7,
        },
        headers=_auth_headers(token, client_mutation_id or str(uuid4())),
    )


def _delete_invitation(
    client: TestClient,
    *,
    token: str,
    project_id: int,
    invitation_id: int,
    client_mutation_id: str | None = None,
):
    return client.delete(
        f"/api/projects/{project_id}/invitations/{invitation_id}",
        headers=_auth_headers(token, client_mutation_id or str(uuid4())),
    )


def _accept_invitation(
    client: TestClient,
    *,
    token: str,
    invitation_token: str,
    client_mutation_id: str | None = None,
):
    return client.post(
        f"/api/invitations/{invitation_token}/accept",
        headers=_auth_headers(token, client_mutation_id or str(uuid4())),
    )


def _assert_error_code(response, expected_code: str) -> None:
    assert response.json() == {"error": {"code": expected_code}}


def test_owner_can_create_invitation_with_unchanged_response_shape(
    client: TestClient,
) -> None:
    owner = _register_and_login(
        client,
        username="owner_inv_create",
        email="owner_inv_create@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Invite Create")

    response = _create_invitation(
        client,
        token=owner["token"],
        project_id=project["id"],
        role="MANAGER",
        email="new.member@example.com",
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["id"] > 0
    assert payload["token"]
    assert payload["role"] == "MANAGER"
    assert payload["email"] == "new.member@example.com"
    assert payload["maxUses"] == 1
    assert payload["usedCount"] == 0
    assert isinstance(payload["expiresAt"], str)
    assert payload["link"].endswith(payload["token"])


def test_member_cannot_create_invitation(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_inv_member_denied",
        email="owner_inv_member_denied@example.com",
    )
    member = _register_and_login(
        client,
        username="member_inv_denied",
        email="member_inv_denied@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Invite Denied")
    _add_member_via_invite(
        client,
        owner_token=owner["token"],
        member_token=member["token"],
        project_id=project["id"],
    )

    response = _create_invitation(
        client,
        token=member["token"],
        project_id=project["id"],
    )

    assert response.status_code == 403, response.text
    _assert_error_code(response, "INSUFFICIENT_PERMISSIONS")


def test_manager_cannot_create_owner_invitation(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_inv_owner_role",
        email="owner_inv_owner_role@example.com",
    )
    manager = _register_and_login(
        client,
        username="manager_inv_owner_role",
        email="manager_inv_owner_role@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Owner Invite")
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

    response = _create_invitation(
        client,
        token=manager["token"],
        project_id=project["id"],
        role="OWNER",
    )

    assert response.status_code == 403, response.text
    _assert_error_code(response, "INSUFFICIENT_PERMISSIONS")


def test_manager_can_delete_invitation(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_inv_delete",
        email="owner_inv_delete@example.com",
    )
    manager = _register_and_login(
        client,
        username="manager_inv_delete",
        email="manager_inv_delete@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Delete Invite")
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
    invite = _create_invitation(
        client,
        token=owner["token"],
        project_id=project["id"],
    ).json()

    response = _delete_invitation(
        client,
        token=manager["token"],
        project_id=project["id"],
        invitation_id=invite["id"],
    )

    assert response.status_code == 204, response.text
    assert response.content == b""


def test_delete_invitation_not_found(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_inv_delete_missing",
        email="owner_inv_delete_missing@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Delete Missing")

    response = _delete_invitation(
        client,
        token=owner["token"],
        project_id=project["id"],
        invitation_id=999999,
    )

    assert response.status_code == 404, response.text
    _assert_error_code(response, "INVITATION_NOT_FOUND")


def test_accept_invitation_success_and_already_member(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_inv_accept",
        email="owner_inv_accept@example.com",
    )
    member = _register_and_login(
        client,
        username="member_inv_accept",
        email="member_inv_accept@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Accept Invite")
    invite = _create_invitation(
        client,
        token=owner["token"],
        project_id=project["id"],
        max_uses=None,
    ).json()

    first_response = _accept_invitation(
        client,
        token=member["token"],
        invitation_token=invite["token"],
    )
    assert first_response.status_code == 200, first_response.text
    assert first_response.json() == {
        "projectId": project["id"],
        "success": {"code": "INVITATION_ACCEPT_SUCCESS", "params": None},
    }

    second_response = _accept_invitation(
        client,
        token=member["token"],
        invitation_token=invite["token"],
    )
    assert second_response.status_code == 200, second_response.text
    assert second_response.json() == {
        "projectId": project["id"],
        "success": {"code": "ALREADY_PROJECT_MEMBER", "params": None},
    }


def test_accept_invitation_rejects_other_email(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_inv_email",
        email="owner_inv_email@example.com",
    )
    member = _register_and_login(
        client,
        username="member_inv_email",
        email="member_inv_email@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Email Invite")
    invite = _create_invitation(
        client,
        token=owner["token"],
        project_id=project["id"],
        email="someone.else@example.com",
    ).json()

    response = _accept_invitation(
        client,
        token=member["token"],
        invitation_token=invite["token"],
    )

    assert response.status_code == 403, response.text
    _assert_error_code(response, "INVITATION_FOR_OTHER_EMAIL")


def test_accept_invitation_usage_limit(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_inv_limit",
        email="owner_inv_limit@example.com",
    )
    first_member = _register_and_login(
        client,
        username="first_inv_limit",
        email="first_inv_limit@example.com",
    )
    second_member = _register_and_login(
        client,
        username="second_inv_limit",
        email="second_inv_limit@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Limit Invite")
    invite = _create_invitation(
        client,
        token=owner["token"],
        project_id=project["id"],
        max_uses=1,
    ).json()

    first_response = _accept_invitation(
        client,
        token=first_member["token"],
        invitation_token=invite["token"],
    )
    assert first_response.status_code == 200, first_response.text

    second_response = _accept_invitation(
        client,
        token=second_member["token"],
        invitation_token=invite["token"],
    )
    assert second_response.status_code == 410, second_response.text
    _assert_error_code(second_response, "INVITATION_USAGE_LIMIT_REACHED")


def test_invitation_deleted_realtime_contract(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_inv_delete_rt",
        email="owner_inv_delete_rt@example.com",
    )
    manager = _register_and_login(
        client,
        username="manager_inv_delete_rt",
        email="manager_inv_delete_rt@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Delete RT")
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
    invite = _create_invitation(
        client,
        token=owner["token"],
        project_id=project["id"],
    ).json()

    with _auth_project_ws(
        client,
        token=manager["token"],
        project_id=project["id"],
    ) as ws_manager:
        mutation_id = f"invite-delete-{uuid4()}"
        response = _delete_invitation(
            client,
            token=owner["token"],
            project_id=project["id"],
            invitation_id=invite["id"],
            client_mutation_id=mutation_id,
        )
        assert response.status_code == 204, response.text

        event = _receive_event(ws_manager, RealtimeEventType.INVITATION_DELETED)
        assert event["payload"]["invitationId"] == invite["id"]
        assert event["clientMutationId"] == mutation_id


def test_invitation_accept_realtime_contract(client: TestClient) -> None:
    owner = _register_and_login(
        client,
        username="owner_inv_accept_rt",
        email="owner_inv_accept_rt@example.com",
    )
    member = _register_and_login(
        client,
        username="member_inv_accept_rt",
        email="member_inv_accept_rt@example.com",
    )
    project = _create_project(client, token=owner["token"], name="Accept RT")
    invite = _create_invitation(
        client,
        token=owner["token"],
        project_id=project["id"],
    ).json()

    with _auth_project_ws(
        client,
        token=owner["token"],
        project_id=project["id"],
    ) as ws_project:
        with _auth_user_ws(client, token=member["token"]) as ws_user:
            mutation_id = f"invite-accept-{uuid4()}"
            response = _accept_invitation(
                client,
                token=member["token"],
                invitation_token=invite["token"],
                client_mutation_id=mutation_id,
            )
            assert response.status_code == 200, response.text

            member_event = _receive_event(ws_project, RealtimeEventType.MEMBER_ADDED)
            assert member_event["payload"]["userId"] == member["user"]["id"]
            assert member_event["payload"]["role"] == "MEMBER"
            assert member_event["clientMutationId"] == mutation_id

            user_event = _receive_event(
                ws_user,
                RealtimeEventType.PROJECT_ADDED_TO_USER,
            )
            assert user_event["payload"]["projectId"] == project["id"]
            assert user_event["clientMutationId"] == mutation_id
