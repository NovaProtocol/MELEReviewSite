from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def _unique_name(prefix: str = "user") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def test_login_sets_secure_cookie(client):
    """login Set-Cookie must contain HttpOnly, SameSite=Lax, Max-Age, Path=/"""
    name = _unique_name("CookieUser")
    res = client.post("/api/auth/accounts", json={"name": name, "pin": "1234"})
    assert res.status_code == 201, res.text
    account_id = res.json()["id"]

    res = client.post("/api/auth/login", json={"account_id": account_id, "pin": "1234"})
    assert res.status_code == 200

    set_cookie = res.headers.get("set-cookie", "")
    # httponly
    assert "httponly" in set_cookie.lower(), f"HttpOnly missing in {set_cookie}"
    # samesite=lax
    assert "samesite=lax" in set_cookie.lower(), f"SameSite=Lax missing in {set_cookie}"
    # max-age 30 days = 2592000
    assert "max-age=2592000" in set_cookie.lower(), f"Max-Age=2592000 missing in {set_cookie}"
    # path=/
    assert "path=/" in set_cookie.lower(), f"Path=/ missing in {set_cookie}"
    # secure flag should match DEBUG: in debug mode secure is False, not present; but check httponly etc
    # If DEBUG False, Secure should be present; we just verify httponly etc are required


def test_login_rate_limited(client):
    """6 rapid logins should 429 on 6th"""
    # Reset limiter storage to isolate this test from prior requests
    try:
        from api.routes.auth import limiter as auth_limiter

        auth_limiter.reset()
    except Exception:
        pass
    try:
        from api.app import app as fastapi_app

        if hasattr(fastapi_app.state, "limiter"):
            fastapi_app.state.limiter.reset()
    except Exception:
        pass

    name = _unique_name("RateUser")
    res = client.post("/api/auth/accounts", json={"name": name, "pin": "9999"})
    assert res.status_code == 201, res.text
    account_id = res.json()["id"]

    # Reset again after account creation so only logins are counted
    try:
        from api.routes.auth import limiter

        limiter.reset()
    except Exception:
        pass

    last_status = None
    for i in range(6):
        r = client.post("/api/auth/login", json={"account_id": account_id, "pin": "9999"})
        last_status = r.status_code
        if i < 5:
            assert r.status_code == 200, f"attempt {i+1} expected 200 got {r.status_code}: {r.text}"
        else:
            assert r.status_code == 429, f"6th attempt expected 429 got {r.status_code}: {r.text}"


def test_account_create_validation_rejects_bad_name(client):
    """AccountCreate validates name 1-50 pattern ^[A-Za-z0-9 _-]+$"""
    # too short / empty
    r = client.post("/api/auth/accounts", json={"name": "", "pin": "1234"})
    assert r.status_code == 422, f"empty name should 422 got {r.status_code}"
    # invalid characters
    r = client.post("/api/auth/accounts", json={"name": "bad!@#", "pin": "1234"})
    assert r.status_code == 422
    # too long 51 chars
    r = client.post("/api/auth/accounts", json={"name": "a" * 51, "pin": "1234"})
    assert r.status_code == 422


def test_account_create_validation_rejects_bad_pin(client):
    """pin 4-20"""
    r = client.post("/api/auth/accounts", json={"name": _unique_name("PinUser"), "pin": "123"})
    assert r.status_code == 422, f"pin too short should 422 got {r.status_code}"
    r = client.post("/api/auth/accounts", json={"name": _unique_name("PinUser"), "pin": "a" * 21})
    assert r.status_code == 422


def test_duplicate_account_returns_409(client):
    """duplicate name should 409"""
    name = _unique_name("DupUser")
    r = client.post("/api/auth/accounts", json={"name": name, "pin": "1234"})
    assert r.status_code == 201
    r2 = client.post("/api/auth/accounts", json={"name": name, "pin": "1234"})
    assert r2.status_code == 409, f"duplicate should 409 got {r2.status_code}: {r2.text}"
