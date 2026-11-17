"""Settings parsing, including the values compose actually hands the container."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings

BASE_ENV = {
    "MYSQL_PASS": "x",
    "SECRET_KEY": "a" * 32,
}


def _settings(monkeypatch, **env) -> Settings:
    for key in (
        "COOKIE_SECURE",
        "DEPLOYMENT_TYPE",
        "ADMIN_USER",
        "ADMIN_PASS",
        "DATABASE_URL",
        "MAX_OPEN_INVITES",
        "UPLOAD_DIR",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings(**BASE_ENV)


def test_an_empty_cookie_secure_is_treated_as_unset(monkeypatch):
    """Compose passes `${COOKIE_SECURE:-}` as an empty string.

    Pydantic will not parse `""` as a boolean, and the failure happened at import,
    which crash-looped the container on the first real deployment.
    """
    settings = _settings(monkeypatch, COOKIE_SECURE="", DEPLOYMENT_TYPE="production")
    assert settings.COOKIE_SECURE is None
    assert settings.secure_cookies is True


def test_an_empty_cookie_secure_in_debug_still_yields_plain_http(monkeypatch):
    settings = _settings(monkeypatch, COOKIE_SECURE="", DEPLOYMENT_TYPE="debug")
    assert settings.COOKIE_SECURE is None
    assert settings.secure_cookies is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("true", True), ("false", False), ("1", True), ("0", False)],
)
def test_cookie_secure_parses_explicit_values(monkeypatch, raw, expected):
    settings = _settings(monkeypatch, COOKIE_SECURE=raw)
    assert settings.COOKIE_SECURE is expected


def test_cookie_secure_falls_back_to_the_deployment_type(monkeypatch):
    assert _settings(monkeypatch, DEPLOYMENT_TYPE="production").secure_cookies is True
    assert _settings(monkeypatch, DEPLOYMENT_TYPE="debug").secure_cookies is False


def test_secret_key_must_be_long_enough(monkeypatch):
    for key in ("COOKIE_SECURE", "DEPLOYMENT_TYPE"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValidationError):
        Settings(MYSQL_PASS="x", SECRET_KEY="short")


def test_db_url_is_built_from_the_parts(monkeypatch):
    monkeypatch.setenv("MYSQL_HOST", "dbhost")
    settings = _settings(monkeypatch)
    assert settings.db_url == "mysql+aiomysql://root:x@dbhost:3306/MELEReview"


def test_database_url_overrides_the_parts(monkeypatch):
    settings = _settings(monkeypatch, DATABASE_URL="sqlite+aiosqlite:////tmp/x.db")
    assert settings.db_url == "sqlite+aiosqlite:////tmp/x.db"


def test_upload_dir_is_a_path(monkeypatch):
    settings = _settings(monkeypatch, UPLOAD_DIR="/tmp/uploads")
    assert str(settings.upload_dir) == "/tmp/uploads"


def test_the_example_admin_password_is_recognised():
    """A deployment left on the documented default is a published master key."""
    from app.config import Settings

    base = {"SECRET_KEY": "x" * 40, "MYSQL_PASS": "m"}
    assert Settings(**base, ADMIN_PASS="password").admin_password_is_default
    assert Settings(**base, ADMIN_PASS="Password").admin_password_is_default
    assert not Settings(**base, ADMIN_PASS="a-real-long-one").admin_password_is_default


def test_a_production_boot_refuses_the_example_password(monkeypatch):
    """Refused with an instruction, not started with the hole open."""
    import asyncio

    import pytest

    from app import lifespan
    from app.config import get_config

    config = get_config()
    monkeypatch.setattr(config, "ADMIN_PASS", "password", raising=False)
    monkeypatch.setattr(config, "DEPLOYMENT_TYPE", "production", raising=False)
    monkeypatch.setattr(config, "COOKIE_SECURE", True, raising=False)

    async def run():
        from fastapi import FastAPI

        app = FastAPI(lifespan=lifespan)
        async with app.router.lifespan_context(app):
            pass

    with pytest.raises(RuntimeError, match="ADMIN_PASS"):
        asyncio.run(run())
