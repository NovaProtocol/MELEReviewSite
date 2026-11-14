from pathlib import Path

import yaml


def test_compose_uses_the_house_port_block():
    data = yaml.safe_load(Path("compose.yaml").read_text())
    main = data["services"]["melereview_main"]
    caddy = data["services"]["caddy"]
    assert "7061" in [str(port) for port in main["expose"]]
    assert caddy["ports"] == ["127.0.0.1:7060:7060"]


def test_compose_passes_the_admin_credentials():
    data = yaml.safe_load(Path("compose.yaml").read_text())
    env = data["services"]["melereview_main"]["environment"]
    assert env["ADMIN_USER"] == "${ADMIN_USER:?ADMIN_USER is required}"
    assert env["ADMIN_PASS"] == "${ADMIN_PASS:?ADMIN_PASS is required}"


def test_compose_requires_every_secret_fail_fast():
    data = yaml.safe_load(Path("compose.yaml").read_text())
    env = data["services"]["melereview_main"]["environment"]
    for name in ("DEPLOYMENT_TYPE", "MYSQL_PASS", "SECRET_KEY"):
        assert ":?" in env[name], name


def test_compose_has_healthchecks_and_volume_for_uploads():
    data = yaml.safe_load(Path("compose.yaml").read_text())
    assert "healthcheck" in data["services"]["melereview_main"]
    assert "healthcheck" in data["services"]["mysql-db"]
    main = data["services"]["melereview_main"]
    assert main["depends_on"]["mysql-db"]["condition"] == "service_healthy"
    assert any("uploads_data" in str(volume) for volume in main["volumes"])
    assert "uploads_data" in data["volumes"]


def test_caddy_proxies_the_container_name_and_not_the_service_name():
    source = Path("caddy/Caddyfile").read_text()
    assert "reverse_proxy melereview_main:7061" in source
    assert "reverse_proxy app:" not in source
    assert "forward_auth" not in source


def test_caddy_caches_static_with_the_replace_form():
    source = Path("caddy/Caddyfile").read_text()
    static_block = source.split("handle /static/*")[1].split("\n\t}")[0]
    assert ">Cache-Control" in static_block
    assert "reverse_proxy melereview_main:7061" in static_block


def test_caddy_serves_health_and_documentation():
    source = Path("caddy/Caddyfile").read_text()
    assert "handle /health" in source
    assert "handle_path /documentation/*" in source
    assert "reverse_proxy melereview_documentation:8005" in source


def test_dockerfile_runs_non_root_and_builds_deps_first():
    source = Path("Dockerfile").read_text()
    assert "python:3.14-slim AS builder" in source
    assert source.index("COPY requirements.txt") < source.index("COPY app/")
    assert "useradd --create-home --uid 10001 appuser" in source
    assert "USER appuser" in source
    assert 'CMD ["granian"' in source


def test_env_example_documents_every_variable():
    source = Path(".env.example").read_text()
    for name in (
        "DEPLOYMENT_TYPE",
        "MYSQL_PASS",
        "SECRET_KEY",
        "ADMIN_USER",
        "ADMIN_PASS",
        "UPLOAD_DIR",
        "MAX_UPLOAD_BYTES",
        "MAX_OPEN_INVITES",
        "COOKIE_SECURE",
    ):
        assert name in source, name


def test_no_retired_directories_remain():
    for path in ("api", "web", "proto", "alembic"):
        assert not Path(path).exists(), path
    assert not Path("alembic.ini").exists()
