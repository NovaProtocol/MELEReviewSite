from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_ROOT = tempfile.mkdtemp(prefix="melereview-uploads-")

os.environ.setdefault("SECRET_KEY", "test-secret-key-must-be-at-least-32-chars")
os.environ.setdefault("DEPLOYMENT_TYPE", "debug")
os.environ.setdefault("MYSQL_PASS", "test-pass")
os.environ.setdefault("ADMIN_USER", "admin")
os.environ.setdefault("ADMIN_PASS", "password")
os.environ.setdefault("UPLOAD_DIR", UPLOAD_ROOT)
os.environ.setdefault("MAX_OPEN_INVITES", "200")
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/melereview_test.db"

sys.path.insert(0, BASE)

from app import create_app  # noqa: E402
from app.db import _get_engine  # noqa: E402

app = create_app()

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture(scope="session", autouse=True)
def _clean_state():
    pathlib.Path("/tmp/melereview_test.db").unlink(missing_ok=True)
    yield
    pathlib.Path("/tmp/melereview_test.db").unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def _reset_limiter():
    from app.limiter import limiter

    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def client():
    """A fresh browser per test: the app is shared, the cookie jar is not."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def admin_client(client):
    """A signed-in system administrator client.

    The administrator is created by bootstrap from ADMIN_USER / ADMIN_PASS, so the
    fixture signs in rather than inserting a row: it exercises the real path.
    """
    client.get("/")
    token = client.cookies.get("melereview_csrf")
    assert token
    response = client.post(
        "/api/auth/login",
        json={"identifier": "admin", "password": "password"},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200, response.text
    return client


def register_with_invite(client, code: str, username: str, password: str = "password123"):
    """Redeem a code on a bare client, returning the new user's payload."""
    token = client.cookies.get("melereview_csrf") or ""
    return client.post(
        "/api/auth/register",
        json={
            "invite_code": code,
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
        },
        headers={"X-CSRF-Token": token},
    )


def new_invite(client) -> str:
    token = client.cookies.get("melereview_csrf")
    response = client.post("/api/invites", headers={"X-CSRF-Token": token})
    assert response.status_code == 201, response.text
    return response.json()["code"]


class Member:
    """A second signed-in browser, so registering never disturbs the admin jar.

    ``username`` is the real, unique name the account was created with; tests that
    look the account up in the admin list must use it rather than the label they
    asked for.
    """

    def __init__(self, username: str, password: str, client, label: str = "") -> None:
        self.username = username
        self.label = label or username
        self.password = password
        self.client = client

    def invite_code(self) -> str:
        return new_invite(self.client)

    def create_invitee(
        self, username: str, password: str = "password123"
    ) -> tuple[dict, TestClient]:
        """Mint a code as this member and redeem it on a fresh client."""
        code = self.invite_code()
        new_client = TestClient(app)
        new_client.__enter__()
        new_client.get("/")
        response = register_with_invite(new_client, code, username, password)
        assert response.status_code == 201, response.text
        return response.json(), new_client


@pytest.fixture
def member_factory(admin_client):
    """Create a signed-in member under the admin, each with its own cookie jar.

    The username is suffixed per test, so two modules can both ask for a member
    called "author" without colliding in the shared test database.
    """

    created: list[Member] = []

    def _make(username: str, password: str = "password123") -> Member:
        unique = f"{username[:20]}_{uuid.uuid4().hex[:6]}"
        code = new_invite(admin_client)
        browser = TestClient(app)
        browser.__enter__()
        browser.get("/")
        response = register_with_invite(browser, code, unique, password)
        assert response.status_code == 201, response.text
        member = Member(unique, password, browser, label=username)
        created.append(member)
        return member

    yield _make
    for member in created:
        member.client.__exit__(None, None, None)


@pytest.fixture
def engine():
    return _get_engine()
