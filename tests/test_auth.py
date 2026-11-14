from __future__ import annotations

from app.security import hash_password, verify_password


def test_password_round_trips():
    stored = hash_password("correct horse battery")
    assert stored.startswith("scrypt$")
    assert verify_password("correct horse battery", stored)
    assert not verify_password("wrong horse battery", stored)


def test_password_hash_is_salted():
    first = hash_password("same password")
    second = hash_password("same password")
    assert first != second
    assert verify_password("same password", first)
    assert verify_password("same password", second)


def test_garbage_hash_never_matches():
    assert not verify_password("anything", None)
    assert not verify_password("anything", "")
    assert not verify_password("anything", "not-a-hash")
    assert not verify_password("anything", "bcrypt$x$y")


def test_login_with_username(client, admin_client):
    admin_client.get("/")
    token = admin_client.cookies.get("melereview_csrf")
    response = admin_client.post(
        "/api/auth/login",
        json={"identifier": "admin", "password": "password"},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200
    assert response.json()["username"] == "admin"
    assert response.json()["is_system_admin"] is True


def test_login_with_email(client, admin_client):
    admin_client.get("/")
    token = admin_client.cookies.get("melereview_csrf")
    response = admin_client.post(
        "/api/auth/login",
        json={"identifier": "admin@melereview.local", "password": "password"},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200


def test_login_rejects_wrong_password(client):
    client.get("/")
    token = client.cookies.get("melereview_csrf")
    response = client.post(
        "/api/auth/login",
        json={"identifier": "admin", "password": "not-the-password"},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 401


def test_session_cookie_is_httponly_lax(client):
    client.get("/")
    token = client.cookies.get("melereview_csrf")
    response = client.post(
        "/api/auth/login",
        json={"identifier": "admin", "password": "password"},
        headers={"X-CSRF-Token": token},
    )
    cookie = response.headers.get("set-cookie", "").lower()
    assert "melereview_session=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie


def test_mutation_without_csrf_is_refused(client, admin_client):
    response = admin_client.post("/api/invites", headers={"X-CSRF-Token": ""})
    assert response.status_code == 403


def test_changing_username_keeps_uid(client, admin_client):
    from conftest import new_invite

    code = new_invite(admin_client)
    token = admin_client.cookies.get("melereview_csrf")
    registered = admin_client.post(
        "/api/auth/register",
        json={
            "invite_code": code,
            "username": "renamable",
            "email": "renamable@example.com",
            "password": "password123",
        },
        headers={"X-CSRF-Token": token},
    )
    assert registered.status_code == 201
    original_uid = registered.json()["uid"]
    renamed = admin_client.put(
        "/api/auth/username",
        json={"username": "renamed_user"},
        headers={"X-CSRF-Token": token},
    )
    assert renamed.status_code == 200
    assert renamed.json()["username"] == "renamed_user"
    assert renamed.json()["uid"] == original_uid


def test_signed_out_user_cannot_read_profile(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/library", follow_redirects=False).status_code == 302
