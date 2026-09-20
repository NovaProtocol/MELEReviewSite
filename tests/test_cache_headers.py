"""Cache-Control precedence for the API, the web service and the docs service.

Each of the three carries its own copy of the middleware, so each is checked
here. The behaviour they must share: a response that sets its own
``Cache-Control`` keeps it, and only a response that sets none is given the
deployment's answer.

The reason this matters is the site sits behind GateKeeper. While the precedence
was wrong, a resource that deliberately published its own lifespan was pinned to
``no-store`` on every request, which is what made caching impossible anywhere on
the deployment.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM_CACHE = "public, max-age=300"


def load(path: str, name: str) -> Any:
    """Load a cache module by path, because the copies share one file name."""
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WEB_CACHE = load("web/cache.py", "melereview_web_cache")
API_CACHE = load("api/cache.py", "melereview_api_cache")
DOCS_CACHE = load("documentation/cache.py", "melereview_docs_cache")

COPIES = [
    pytest.param(WEB_CACHE, id="web"),
    pytest.param(API_CACHE, id="api"),
    pytest.param(DOCS_CACHE, id="documentation"),
]


def build(cache: Any, is_debug: bool, headers: dict[str, str] | None = None) -> FastAPI:
    app = FastAPI()

    @app.get("/thing")
    async def _route() -> PlainTextResponse:
        return PlainTextResponse("ok", headers=dict(headers or {}))

    app.add_middleware(cache.CacheControlMiddleware, is_debug=is_debug)  # type: ignore[arg-type]
    return app


@pytest.mark.parametrize("cache", COPIES)
@pytest.mark.parametrize("is_debug", [True, False])
def test_a_response_that_sets_its_own_policy_keeps_it(cache: Any, is_debug: bool) -> None:
    with TestClient(build(cache, is_debug, {"Cache-Control": UPSTREAM_CACHE})) as client:
        response = client.get("/thing")

    assert response.headers["Cache-Control"] == UPSTREAM_CACHE


@pytest.mark.parametrize("cache", COPIES)
def test_a_response_with_no_policy_is_no_store_in_debug(cache: Any) -> None:
    with TestClient(build(cache, True)) as client:
        response = client.get("/thing")

    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("cache", COPIES)
def test_a_static_path_is_public_in_production(cache: Any) -> None:
    app = FastAPI()

    @app.get("/static/app.css")
    async def _static() -> PlainTextResponse:
        return PlainTextResponse("body{}", media_type="text/css")

    app.add_middleware(cache.CacheControlMiddleware, is_debug=False)  # type: ignore[arg-type]

    with TestClient(app) as client:
        response = client.get("/static/app.css")

    assert response.headers["Cache-Control"] == "public, max-age=86400"


@pytest.mark.parametrize("cache", COPIES)
def test_an_api_path_is_private_no_store_in_production(cache: Any) -> None:
    """Per-visitor JSON may never rest in a shared cache."""
    app = FastAPI()

    @app.get("/api/questions")
    async def _api() -> PlainTextResponse:
        return PlainTextResponse("[]", media_type="application/json")

    app.add_middleware(cache.CacheControlMiddleware, is_debug=False)  # type: ignore[arg-type]

    with TestClient(app) as client:
        response = client.get("/api/questions")

    assert response.headers["Cache-Control"] == "private, no-store"


@pytest.mark.parametrize("cache", COPIES)
def test_health_keeps_a_public_lifespan_in_production(cache: Any) -> None:
    app = FastAPI()

    @app.get("/health")
    async def _health() -> PlainTextResponse:
        return PlainTextResponse("ok")

    app.add_middleware(cache.CacheControlMiddleware, is_debug=False)  # type: ignore[arg-type]

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.headers["Cache-Control"] == "public, max-age=3600"


def test_is_debug_deployment_treats_an_absent_value_as_production() -> None:
    """The web and docs services carry no ``DEPLOYMENT_TYPE``.

    They take the production branch as a result, which is what gives ``/static``
    its day-long lifespan. Setting it to ``debug`` would turn every static
    response into ``no-store``, so this is the behaviour to keep in mind before
    adding the variable to either service.
    """
    for cache in (WEB_CACHE, API_CACHE, DOCS_CACHE):
        saved = os.environ.pop("DEPLOYMENT_TYPE", None)
        try:
            assert cache.is_debug_deployment() is False
            os.environ["DEPLOYMENT_TYPE"] = "debug"
            assert cache.is_debug_deployment() is True
            os.environ["DEPLOYMENT_TYPE"] = "DEBUG"
            assert cache.is_debug_deployment() is True
            os.environ["DEPLOYMENT_TYPE"] = "production"
            assert cache.is_debug_deployment() is False
        finally:
            os.environ.pop("DEPLOYMENT_TYPE", None)
            if saved is not None:
                os.environ["DEPLOYMENT_TYPE"] = saved


def test_the_two_application_copies_stay_identical() -> None:
    """They are duplicated on purpose, so a divergence must be deliberate."""
    api = (ROOT / "api/cache.py").read_text().replace(" (api copy)", "")
    web = (ROOT / "web/cache.py").read_text()

    assert api == web
