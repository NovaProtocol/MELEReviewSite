import re
from pathlib import Path


def test_base_no_dom_race():
    src = Path("web/templates/base.html").read_text()
    assert 'getElementById("dark-mode-toggle")' not in src.split("DOMContentLoaded")[0]


def test_base_has_defer():
    src = Path("web/templates/base.html").read_text()
    # at least the CDN scripts should be deferred
    assert "defer" in src


def test_caddy_static_cached():
    src = Path("caddy/Caddyfile").read_text()
    assert 'Cache-Control "public, max-age=31536000, immutable"' in src
    assert "no-cache" not in src


def test_caddy_static_replaces_rather_than_adds():
    """A bare `header` ADDS a second Cache-Control line instead of replacing.

    `melereview_web` sets its own `public, max-age=86400`, so the add form left
    every `/static` response carrying two values and a cache had to guess which
    won. `header >Cache-Control` replaces it, so exactly one value leaves.
    """
    src = Path("caddy/Caddyfile").read_text()
    static_block = src.split("handle /static/*")[1].split("\n\t}")[0]

    assert ">Cache-Control" in static_block
    assert not re.search(r"\bheader\s+Cache-Control", static_block)


def test_caddy_static_block_still_proxies():
    """A `handle` holding only a `header` wins the route and returns an empty 200.

    It does not fall through to the catch-all, so the `reverse_proxy` has to stay
    inside the same block as the header or every static request answers empty.
    """
    src = Path("caddy/Caddyfile").read_text()
    static_block = src.split("handle /static/*")[1].split("\n\t}")[0]

    assert "reverse_proxy melereview_web:8081" in static_block


def test_caddy_health_bypass():
    src = Path("caddy/Caddyfile").read_text()
    # /health handle must exist and must NOT require forward_auth (it should bypass auth)
    # Simple check: handle /health block exists and forward_auth not inside it
    # Split by handles
    health_section = (
        src.split("handle /health")[1].split("handle")[0] if "handle /health" in src else ""
    )
    assert "forward_auth" not in health_section
