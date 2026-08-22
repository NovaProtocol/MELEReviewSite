from pathlib import Path


def test_grpc_proto_exists():
    assert Path("api/proto/api.proto").exists()


def test_grpc_proto_has_service():
    txt = Path("api/proto/api.proto").read_text()
    assert 'syntax = "proto3"' in txt
    assert "service Review" in txt
    assert "rpc GetQuestions" in txt
    assert "Empty" in txt
    assert "QuestionList" in txt


def test_grpc_server_exists():
    p = Path("api/grpc_server.py")
    assert p.exists()
    txt = p.read_text()
    assert "grpc.aio" in txt
    assert "add_ReviewServicer_to_server" in txt
    assert "add_insecure_port" in txt
    assert "[::]:50051" in txt


def test_grpc_client_exists():
    # either web/grpc_client.py or api/grpc_client.py
    web = Path("web/grpc_client.py")
    api_c = Path("api/grpc_client.py")
    assert web.exists() or api_c.exists()
    txt = web.read_text() if web.exists() else api_c.read_text()
    assert "grpc" in txt
    assert "50051" in txt or "melereview_api" in txt


def test_compose_exposes_grpc_internal_only():
    import yaml

    data = yaml.safe_load(Path("compose.yaml").read_text())
    api = data["services"]["melereview_api"]
    # expose must contain 50051
    expose = api.get("expose", [])
    assert any("50051" in str(e) for e in expose), f"expose missing 50051: {expose}"
    # ports must NOT contain 50051 (internal only)
    ports = api.get("ports", [])
    # ports may be absent or empty; ensure none maps 50051
    assert not any("50051" in str(p) for p in ports), f"ports should not expose 50051: {ports}"
    # networks should include default
    nets = api.get("networks", [])
    assert "default" in nets
    # caddy should NOT expose 50051
    if "caddy" in data["services"]:
        caddy_ports = data["services"]["caddy"].get("ports", [])
        assert not any("50051" in str(p) for p in caddy_ports)


def test_requirements_has_grpc():
    txt = Path("api/requirements.txt").read_text().lower()
    assert "grpcio" in txt
    assert "grpcio-tools" in txt
    assert "protobuf" in txt


def test_http_still_public_via_caddy():
    txt = Path("caddy/Caddyfile").read_text()
    assert "melereview_api:8082" in txt
    assert "melereview_web:8081" in txt
    # caddy should not proxy grpc port
    assert "50051" not in txt
