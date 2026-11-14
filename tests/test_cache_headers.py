"""Cache-Control precedence on the single middleware this app now carries."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM_CACHE = "public, max-age=300"


def load_cache() -> Any:
    spec = importlib.util.spec_from_file_location("melereview_cache", ROOT / "app/cache.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CACHE = load_cache()


def build(is_debug: bool, headers: dict[str, str] | None = None) -> FastAPI:
    app = FastAPI()

    @app.get("/thing")
    async def _route() -> PlainTextResponse:
        return PlainTextResponse("ok", headers=dict(headers or {}))

    app.add_middleware(CACHE.CacheControlMiddleware, is_debug=is_debug)
    return app


@pytest.mark.parametrize("is_debug", [True, False])
def test_a_response_that_sets_its_own_policy_keeps_it_in_production_only(is_debug):
    with TestClient(build(is_debug, {"Cache-Control": UPSTREAM_CACHE})) as client:
        response = client.get("/thing")
    expected = "no-store" if is_debug else UPSTREAM_CACHE
    assert response.headers["Cache-Control"] == expected


def test_nothing_is_cacheable_in_debug():
    with TestClient(build(True)) as client:
        assert client.get("/thing").headers["Cache-Control"] == "no-store"


def test_a_static_path_is_public_in_production():
    app = FastAPI()

    @app.get("/static/app.css")
    async def _static() -> PlainTextResponse:
        return PlainTextResponse("body{}", media_type="text/css")

    app.add_middleware(CACHE.CacheControlMiddleware, is_debug=False)
    with TestClient(app) as client:
        response = client.get("/static/app.css")
    assert response.headers["Cache-Control"] == "public, max-age=86400"


@pytest.mark.parametrize("path", ["/api/questions", "/media/solutions/x.png", "/library"])
def test_per_visitor_paths_are_private_and_uncacheable_in_production(path):
    app = FastAPI()

    @app.get(path)
    async def _route() -> PlainTextResponse:
        return PlainTextResponse("x")

    app.add_middleware(CACHE.CacheControlMiddleware, is_debug=False)
    with TestClient(app) as client:
        response = client.get(path)
    assert response.headers["Cache-Control"] == "private, no-store"


def test_health_keeps_a_public_lifespan_in_production():
    app = FastAPI()

    @app.get("/health")
    async def _health() -> PlainTextResponse:
        return PlainTextResponse("ok")

    app.add_middleware(CACHE.CacheControlMiddleware, is_debug=False)
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.headers["Cache-Control"] == "public, max-age=3600"


def test_is_debug_deployment_treats_an_absent_value_as_production(monkeypatch):
    monkeypatch.delenv("DEPLOYMENT_TYPE", raising=False)
    assert CACHE.is_debug_deployment() is False
    monkeypatch.setenv("DEPLOYMENT_TYPE", "debug")
    assert CACHE.is_debug_deployment() is True
    monkeypatch.setenv("DEPLOYMENT_TYPE", "DEBUG")
    assert CACHE.is_debug_deployment() is True
    monkeypatch.setenv("DEPLOYMENT_TYPE", "production")
    assert CACHE.is_debug_deployment() is False
