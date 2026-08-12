from __future__ import annotations

import os
import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

BASE = os.path.join(os.path.dirname(__file__), "..")

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DEPLOYMENT_TYPE", "debug")
os.environ.setdefault("ACCESS_PASSWORD", "test-password")
os.environ.setdefault("MYSQL_PASS", "test-pass")
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/melereview_test.db"

sys.path.insert(0, BASE)

from apps import create_app  # noqa: E402

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
