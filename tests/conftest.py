from __future__ import annotations

import os
import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

BASE = os.path.join(os.path.dirname(__file__), "..")

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DEPLOYMENT_TYPE", "debug")
os.environ["MYSQL_PASS"] = "test-pass"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/melereview_test.db"

sys.path.insert(0, BASE)

from api.app import create_app  # noqa: E402

app = create_app()


@pytest.fixture(scope="session", autouse=True)
def _clean_test_db():
    path = "/tmp/melereview_test.db"
    pathlib.Path(path).unlink(missing_ok=True)
    yield
    pathlib.Path(path).unlink(missing_ok=True)


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
