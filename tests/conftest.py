from __future__ import annotations

import os
import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

BASE = os.path.join(os.path.dirname(__file__), "..")

os.environ.setdefault("SECRET_KEY", "test-secret-key-must-be-at-least-32-chars")
os.environ.setdefault("DEPLOYMENT_TYPE", "debug")
os.environ.setdefault("MYSQL_PASS", "test-pass")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:////tmp/melereview_test.db")

sys.path.insert(0, BASE)

from api.app import create_app  # noqa: E402

app = create_app()


@pytest.fixture(scope="session", autouse=True)
def _clean_test_db():
    # Derive file path from DATABASE_URL so CI override (/tmp/ci.db) is cleaned
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("sqlite"):
        # sqlite+aiosqlite:////tmp/ci.db -> /tmp/ci.db
        path = url.split(":///")[-1] if ":///" in url else "/tmp/melereview_test.db"
    else:
        path = "/tmp/melereview_test.db"
    # Also clean default path to avoid stale state when switching URLs
    for p in {path, "/tmp/melereview_test.db", "/tmp/ci.db"}:
        pathlib.Path(p).unlink(missing_ok=True)
    yield
    for p in {path, "/tmp/melereview_test.db", "/tmp/ci.db"}:
        pathlib.Path(p).unlink(missing_ok=True)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # with-block runs lifespan
        yield c


@pytest.fixture(scope="module")
def account(client):
    """Create an account and log in, returning the client cookie set."""
    res = client.post("/api/auth/accounts", json={"name": "Nova", "pin": "1234"})
    assert res.status_code == 201
    account_id = res.json()["id"]
    res = client.post("/api/auth/login", json={"account_id": account_id, "pin": "1234"})
    assert res.status_code == 200
    return {"id": account_id, "name": "Nova", "cookies": res.cookies}
