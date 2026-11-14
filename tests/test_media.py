from __future__ import annotations

import pytest
from conftest import PNG_BYTES


def _topic_id(client) -> int:
    return client.get("/api/subjects").json()[0]["topics"][0]["id"]


def _question(client, topic_id: int, body: str = "Upload a worked solution") -> dict:
    token = client.cookies.get("melereview_csrf")
    response = client.post(
        "/api/questions",
        json={
            "topic_id": topic_id,
            "body": body,
            "choice_a": "one",
            "choice_b": "two",
            "choice_c": "three",
            "choice_d": "four",
            "correct_choice": "A",
        },
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_upload_stores_a_reference_and_serves_the_bytes(admin_client):
    token = admin_client.cookies.get("melereview_csrf")
    topic_id = _topic_id(admin_client)
    question = _question(admin_client, topic_id)

    upload = admin_client.post(
        f"/api/questions/{question['id']}/solution",
        files={"file": ("worked.png", PNG_BYTES, "image/png")},
        headers={"X-CSRF-Token": token},
    )
    assert upload.status_code == 200, upload.text
    solutions = upload.json()["solutions"]
    assert len(solutions) == 1
    url = solutions[0]["image_url"]
    assert url.startswith("/media/solutions/")

    served = admin_client.get(url)
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"
    assert served.headers["cache-control"] == "private, no-store"
    assert served.content == PNG_BYTES


def test_media_is_not_reachable_without_a_session(admin_client):
    token = admin_client.cookies.get("melereview_csrf")
    topic_id = _topic_id(admin_client)
    question = _question(admin_client, topic_id, "Media needs a session")
    upload = admin_client.post(
        f"/api/questions/{question['id']}/solution",
        files={"file": ("worked.png", PNG_BYTES, "image/png")},
        headers={"X-CSRF-Token": token},
    )
    url = upload.json()["solutions"][0]["image_url"]

    from conftest import app
    from fastapi.testclient import TestClient

    with TestClient(app) as stranger:
        assert stranger.get(url).status_code == 401


def test_upload_replaces_the_previous_solution(admin_client):
    token = admin_client.cookies.get("melereview_csrf")
    topic_id = _topic_id(admin_client)
    question = _question(admin_client, topic_id, "Second upload replaces the first")
    first = admin_client.post(
        f"/api/questions/{question['id']}/solution",
        files={"file": ("a.png", PNG_BYTES, "image/png")},
        headers={"X-CSRF-Token": token},
    )
    first_url = first.json()["solutions"][0]["image_url"]
    second = admin_client.post(
        f"/api/questions/{question['id']}/solution",
        files={"file": ("b.png", PNG_BYTES, "image/png")},
        headers={"X-CSRF-Token": token},
    )
    assert len(second.json()["solutions"]) == 1
    second_url = second.json()["solutions"][0]["image_url"]
    assert second_url != first_url
    assert admin_client.get(first_url).status_code == 404


@pytest.mark.parametrize(
    ("name", "payload", "mime", "expected"),
    [
        ("notanimage.png", b"this is plain text", "image/png", 422),
        ("empty.png", b"", "image/png", 422),
    ],
)
def test_rejects_non_images(admin_client, name, payload, mime, expected):
    token = admin_client.cookies.get("melereview_csrf")
    topic_id = _topic_id(admin_client)
    question = _question(admin_client, topic_id, f"Rejecting {name}")
    response = admin_client.post(
        f"/api/questions/{question['id']}/solution",
        files={"file": (name, payload, mime)},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == expected


def test_rejects_an_oversized_image(admin_client):
    from app.config import get_config

    token = admin_client.cookies.get("melereview_csrf")
    topic_id = _topic_id(admin_client)
    question = _question(admin_client, topic_id, "Too large")
    limit = get_config().MAX_UPLOAD_BYTES
    oversized = PNG_BYTES + b"\x00" * (limit + 1)
    response = admin_client.post(
        f"/api/questions/{question['id']}/solution",
        files={"file": ("big.png", oversized, "image/png")},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 413


def test_avatar_upload_and_replacement(admin_client):
    token = admin_client.cookies.get("melereview_csrf")
    first = admin_client.post(
        "/api/auth/avatar",
        files={"file": ("me.png", PNG_BYTES, "image/png")},
        headers={"X-CSRF-Token": token},
    )
    assert first.status_code == 200, first.text
    url = first.json()["avatar_url"]
    assert url.startswith("/media/avatars/")
    assert admin_client.get(url).status_code == 200

    second = admin_client.post(
        "/api/auth/avatar",
        files={"file": ("me2.png", PNG_BYTES, "image/png")},
        headers={"X-CSRF-Token": token},
    )
    assert second.status_code == 200
    assert admin_client.get(url).status_code == 404


def test_media_path_traversal_is_refused(admin_client):
    assert admin_client.get("/media/../app/config.py").status_code == 404
    assert admin_client.get("/media/%2e%2e/app/config.py").status_code == 404


def test_deleting_a_solution_removes_its_file(admin_client):
    token = admin_client.cookies.get("melereview_csrf")
    topic_id = _topic_id(admin_client)
    question = _question(admin_client, topic_id, "Delete my solution")
    upload = admin_client.post(
        f"/api/questions/{question['id']}/solution",
        files={"file": ("gone.png", PNG_BYTES, "image/png")},
        headers={"X-CSRF-Token": token},
    )
    url = upload.json()["solutions"][0]["image_url"]
    deleted = admin_client.delete(
        f"/api/questions/{question['id']}/solution",
        headers={"X-CSRF-Token": token},
    )
    assert deleted.status_code == 204
    assert admin_client.get(url).status_code == 404
