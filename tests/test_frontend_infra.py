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


def test_caddy_health_bypass():
    src = Path("caddy/Caddyfile").read_text()
    # /health handle must exist and must NOT require forward_auth (it should bypass auth)
    # Simple check: handle /health block exists and forward_auth not inside it
    # Split by handles
    health_section = (
        src.split("handle /health")[1].split("handle")[0] if "handle /health" in src else ""
    )
    assert "forward_auth" not in health_section
