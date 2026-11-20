from __future__ import annotations

import pytest
from conftest import Member, new_invite


def _user_row(admin_client, username: str) -> dict:
    users = admin_client.get("/api/admin/users?per_page=200").json()["items"]
    return next(u for u in users if u["username"] == username)


def test_registration_requires_a_valid_code(client):
    client.get("/")
    token = client.cookies.get("melereview_csrf")
    response = client.post(
        "/api/auth/register",
        json={
            "invite_code": "0123456789abcdef",
            "username": "nosuchcode",
            "email": "nosuchcode@example.com",
            "password": "password123",
        },
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 400


def test_code_cannot_be_used_twice(admin_client):
    code = new_invite(admin_client)
    token = admin_client.cookies.get("melereview_csrf")
    payload = {
        "invite_code": code,
        "username": "firstuser",
        "email": "firstuser@example.com",
        "password": "password123",
    }
    first = admin_client.post("/api/auth/register", json=payload, headers={"X-CSRF-Token": token})
    assert first.status_code == 201
    second = admin_client.post(
        "/api/auth/register",
        json={**payload, "username": "seconduser", "email": "seconduser@example.com"},
        headers={"X-CSRF-Token": token},
    )
    assert second.status_code == 400


def test_invited_by_is_recorded(admin_client):
    code = new_invite(admin_client)
    from conftest import app
    from fastapi.testclient import TestClient

    # Register on its own browser: registration signs the new account in, which
    # would replace the administrator's session in a shared cookie jar.
    with TestClient(app) as newcomer:
        newcomer.get("/")
        token = newcomer.cookies.get("melereview_csrf")
        registered = newcomer.post(
            "/api/auth/register",
            json={
                "invite_code": code,
                "username": "recordedinvitee",
                "email": "recordedinvitee@example.com",
                "password": "password123",
            },
            headers={"X-CSRF-Token": token},
        )
        assert registered.status_code == 201
        assert registered.json()["invited_by"] is not None

    invites = admin_client.get("/api/admin/invites").json()
    used = [i for i in invites if i["code"] == code]
    assert used and used[0]["state"] == "used"


def test_ban_revokes_the_whole_chain(admin_client, member_factory):
    """a invited b, b invited c. Banning a bans a and revokes b and c."""
    token = admin_client.cookies.get("melereview_csrf")
    a_member = member_factory("chainroot")
    a = _user_row(admin_client, a_member.username)
    assert a["invited_by_user_id"] is not None

    b_user, b_client = a_member.create_invitee("chainmiddle")
    b_member = Member(b_user["username"], "password123", b_client)
    c_user, _c_client = b_member.create_invitee("chainleaf")

    preview = admin_client.get(f"/api/admin/users/{a['id']}/ban-preview").json()
    assert preview["total_descendants"] == 2
    assert preview["direct_invitees"] == 1

    result = admin_client.post(
        f"/api/admin/users/{a['id']}/ban", headers={"X-CSRF-Token": token}
    ).json()
    assert result["banned"] == a["id"]
    assert result["revoked"] == 2

    assert _user_row(admin_client, a_member.username)["status"] == "banned"
    assert _user_row(admin_client, b_member.username)["status"] == "revoked"
    leaf = _user_row(admin_client, c_user["username"])
    assert leaf["status"] == "revoked"
    assert leaf["status_root_user_id"] == a["id"]
    assert b_user["id"] != c_user["id"]


def test_revoke_subtree_keeps_the_target_active(admin_client, member_factory):
    token = admin_client.cookies.get("melereview_csrf")
    compromised = member_factory("compromised")
    target = _user_row(admin_client, compromised.username)

    invitee, _client = compromised.create_invitee("collateral")
    invitee_username = invitee["username"]

    preview = admin_client.get(f"/api/admin/users/{target['id']}/ban-preview").json()
    assert preview["total_descendants"] == 1

    result = admin_client.post(
        f"/api/admin/users/{target['id']}/revoke-subtree",
        headers={"X-CSRF-Token": token},
    ).json()
    assert result["revoked"] == 1
    assert result["kept"] == target["id"]

    assert _user_row(admin_client, compromised.username)["status"] == "active"
    assert _user_row(admin_client, invitee_username)["status"] == "revoked"


def test_banned_user_lands_on_the_status_page(admin_client, member_factory):
    token = admin_client.cookies.get("melereview_csrf")
    member = member_factory("tobeban")
    target = _user_row(admin_client, member.username)

    assert member.client.get("/api/auth/me").status_code == 200

    admin_client.post(f"/api/admin/users/{target['id']}/ban", headers={"X-CSRF-Token": token})

    # The session cookie survives, but the row is banned, so the cookie no longer
    # buys anything and the app sends the visitor to the notice.
    assert member.client.get("/api/auth/me").status_code == 401
    landing = member.client.get("/", follow_redirects=False)
    assert landing.status_code == 302
    assert landing.headers["location"] == "/status"
    # The notice is a client page now, so the server owes the shell that boots it. The
    # wording lives in the component; what must hold here is that the page renders for a
    # member who is no longer active.
    notice = member.client.get("/status")
    assert notice.status_code == 200
    assert '<div id="root">' in notice.text
    # The notice reads this, so it must answer for a member who is no longer active.
    status = member.client.get("/api/auth/status").json()
    assert status["username"] == member.username
    assert status["status"] == "banned"


def test_revoked_user_sees_whose_action_it_was(admin_client, member_factory):
    token = admin_client.cookies.get("melereview_csrf")
    root_member = member_factory("revokeroot")
    root = _user_row(admin_client, root_member.username)

    child_user, child_client = root_member.create_invitee("revokedchild")
    child = Member(child_user["username"], "password123", child_client)
    assert child.client.get("/api/auth/me").status_code == 200

    admin_client.post(
        f"/api/admin/users/{root['id']}/revoke-subtree", headers={"X-CSRF-Token": token}
    )

    notice = child.client.get("/status")
    assert notice.status_code == 200
    # Whose action it was, from the endpoint the notice renders: the client says
    # "@root revoked the invitations under them" from these two fields.
    status = child.client.get("/api/auth/status").json()
    assert status["status"] != "active"
    assert status["invited_by"] == root_member.username
    assert status["inviter_status"] == "active"


def test_open_invite_cap_is_enforced(admin_client, monkeypatch):
    from app.config import get_config

    monkeypatch.setattr(get_config(), "MAX_OPEN_INVITES", 2, raising=False)
    token = admin_client.cookies.get("melereview_csrf")
    codes = []
    for _ in range(2):
        response = admin_client.post("/api/invites", headers={"X-CSRF-Token": token})
        assert response.status_code == 201, response.text
        codes.append(response.json()["code"])
    refused = admin_client.post("/api/invites", headers={"X-CSRF-Token": token})
    assert refused.status_code == 409
    assert "unused invitations" in refused.json()["error"]["message"]


def test_invites_of_a_banned_account_are_cancelled(admin_client, member_factory):
    token = admin_client.cookies.get("melereview_csrf")
    member = member_factory("codeholder")
    target = _user_row(admin_client, member.username)
    open_code = member.invite_code()

    admin_client.post(f"/api/admin/users/{target['id']}/ban", headers={"X-CSRF-Token": token})

    invites = admin_client.get("/api/admin/invites").json()
    revoked = [i for i in invites if i["code"] == open_code]
    assert revoked and revoked[0]["state"] == "revoked"


def test_only_the_admin_reaches_the_admin_api(admin_client, member_factory):
    member = member_factory("ordinary")
    assert member.client.get("/api/admin/users").status_code == 403
    assert member.client.get("/admin", follow_redirects=False).status_code == 403
    # Their own invitations stay visible to them.
    assert member.client.get("/api/invites").status_code == 200


def test_admin_can_reactivate_a_banned_account(admin_client, member_factory):
    token = admin_client.cookies.get("melereview_csrf")
    comeback = member_factory("comeback")
    target = _user_row(admin_client, comeback.username)
    admin_client.post(f"/api/admin/users/{target['id']}/ban", headers={"X-CSRF-Token": token})
    assert _user_row(admin_client, comeback.username)["status"] == "banned"

    admin_client.post(
        f"/api/admin/users/{target['id']}/reactivate", headers={"X-CSRF-Token": token}
    )
    assert _user_row(admin_client, comeback.username)["status"] == "active"


@pytest.mark.parametrize("username", ["ab", "has space", "has!bang"])
def test_bad_usernames_are_refused(admin_client, username):
    code = new_invite(admin_client)
    token = admin_client.cookies.get("melereview_csrf")
    response = admin_client.post(
        "/api/auth/register",
        json={
            "invite_code": code,
            "username": username,
            "email": "whatever@example.com",
            "password": "password123",
        },
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 422
