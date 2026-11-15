"""Uploads on disk: avatars, editor images, and solutions."""

from __future__ import annotations

import asyncio

import pytest
from conftest import PNG_BYTES


def _topic_id(client) -> int:
    return client.get("/api/subjects").json()[0]["topics"][0]["id"]


def _question(client, body: str = "A question with a solution") -> dict:
    token = client.cookies.get("melereview_csrf")
    response = client.post(
        "/api/questions",
        json={
            "topic_id": _topic_id(client),
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


def _solution(client, question: dict, body: str = "My working, in prose.") -> dict:
    token = client.cookies.get("melereview_csrf")
    response = client.post(
        f"/api/questions/{question['id']}/solution",
        json={"body": body},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _media(client, name: str = "shot.png", raw: bytes = PNG_BYTES) -> dict:
    token = client.cookies.get("melereview_csrf")
    response = client.post(
        "/api/media",
        files={"file": (name, raw, "image/png")},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_media_stores_a_reference_and_serves_the_bytes(admin_client):
    media = _media(admin_client)
    assert media["url"] == f"/media/{media['uid']}"

    served = admin_client.get(media["url"])
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"
    assert served.headers["cache-control"] == "private, no-store"
    assert served.content == PNG_BYTES


def test_media_is_not_reachable_without_a_session(admin_client):
    url = _media(admin_client)["url"]

    from conftest import app
    from fastapi.testclient import TestClient

    with TestClient(app) as stranger:
        assert stranger.get(url).status_code == 401


@pytest.mark.parametrize(
    ("name", "payload", "mime", "expected"),
    [
        ("notanimage.png", b"this is plain text", "image/png", 422),
        ("empty.png", b"", "image/png", 422),
    ],
)
def test_rejects_non_images(admin_client, name, payload, mime, expected):
    token = admin_client.cookies.get("melereview_csrf")
    response = admin_client.post(
        "/api/media",
        files={"file": (name, payload, mime)},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == expected


def test_rejects_an_oversized_image(admin_client):
    from app.config import get_config

    token = admin_client.cookies.get("melereview_csrf")
    limit = get_config().MAX_MEDIA_BYTES
    oversized = PNG_BYTES + b"\x00" * (limit + 1)
    response = admin_client.post(
        "/api/media",
        files={"file": ("big.png", oversized, "image/png")},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 413


def test_avatar_upload_and_replacement(admin_client):
    token = admin_client.cookies.get("melereview_csrf")
    uid = admin_client.get("/api/auth/me").json()["uid"]
    first = admin_client.post(
        f"/api/users/{uid}/avatar",
        files={"file": ("me.png", PNG_BYTES, "image/png")},
        headers={"X-CSRF-Token": token},
    )
    assert first.status_code == 200, first.text
    url = first.json()["avatar_url"]
    assert url.startswith("/media/avatars/")
    assert admin_client.get(url).status_code == 200

    second = admin_client.post(
        f"/api/users/{uid}/avatar",
        files={"file": ("me2.png", PNG_BYTES, "image/png")},
        headers={"X-CSRF-Token": token},
    )
    assert second.status_code == 200
    assert admin_client.get(url).status_code == 404


def test_media_path_traversal_is_refused(admin_client):
    assert admin_client.get("/media/../app/config.py").status_code == 404
    assert admin_client.get("/media/%2e%2e/app/config.py").status_code == 404


def test_a_solution_is_saved_as_prose(admin_client):
    question = _question(admin_client)
    payload = _solution(admin_client, question, "Use **9.81** and then $v = u + at$.")
    solution = payload["solutions"][0]

    assert "<strong>9.81</strong>" in solution["body_html"]
    assert 'class="math-inline"' in solution["body_html"]
    assert solution["body"] == "Use **9.81** and then $v = u + at$."


def test_saving_again_replaces_rather_than_adds(admin_client):
    question = _question(admin_client)
    _solution(admin_client, question, "First version")
    payload = _solution(admin_client, question, "Second version")

    assert len(payload["solutions"]) == 1
    assert payload["solutions"][0]["body"] == "Second version"


def test_an_empty_solution_is_refused(admin_client):
    question = _question(admin_client)
    token = admin_client.cookies.get("melereview_csrf")
    response = admin_client.post(
        f"/api/questions/{question['id']}/solution",
        json={"body": "   "},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 422


def test_a_solution_carries_an_uploaded_image(admin_client):
    media = _media(admin_client)
    question = _question(admin_client)
    payload = _solution(admin_client, question, f"See the sketch\n\n![]({media['url']})")

    solution = payload["solutions"][0]
    assert media["url"] in solution["body_html"]
    info = admin_client.get(f"/api/media/{media['uid']}/info").json()
    assert info["solution_id"] == solution["id"]
    assert info["question_id"] is None


def test_editing_a_solution_replaces_its_prose(admin_client):
    question = _question(admin_client)
    first = _solution(admin_client, question)["solutions"][0]
    token = admin_client.cookies.get("melereview_csrf")

    edited = admin_client.put(
        f"/api/solutions/{first['id']}",
        json={"body": "A better method, honestly."},
        headers={"X-CSRF-Token": token},
    )
    assert edited.status_code == 200
    assert edited.json()["solutions"][0]["body"] == "A better method, honestly."


def test_a_stranger_cannot_edit_someone_elses_solution(admin_client, member_factory):
    question = _question(admin_client)
    owned = _solution(admin_client, question)["solutions"][0]

    other = member_factory("solutionintruder")
    token = other.client.cookies.get("melereview_csrf")
    response = other.client.put(
        f"/api/solutions/{owned['id']}",
        json={"body": "hijacked"},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 403


def test_deleting_a_solution_deletes_its_images(admin_client):
    media = _media(admin_client)
    question = _question(admin_client)
    solution = _solution(admin_client, question, f"![]({media['url']})")["solutions"][0]
    token = admin_client.cookies.get("melereview_csrf")

    deleted = admin_client.delete(
        f"/api/solutions/{solution['id']}", headers={"X-CSRF-Token": token}
    )
    assert deleted.status_code == 204
    assert admin_client.get(f"/api/media/{media['uid']}/info").status_code == 404
    payload = admin_client.get(f"/api/questions/{question['id']}").json()
    assert payload["solutions"] == []
    assert payload["my_solution"] is None


def test_a_photograph_solution_still_renders(admin_client):
    """Rows written before solutions became prose must keep rendering."""
    from app.db import _get_session_factory
    from app.models import Solution

    question = _question(admin_client, "A legacy solution")

    async def stash() -> None:
        factory = _get_session_factory()
        async with factory() as session:
            session.add(
                Solution(
                    question_id=question["id"],
                    author_user_id=1,
                    image_path="solutions/legacy.png",
                    note="Old style",
                )
            )
            await session.commit()

    asyncio.run(stash())
    payload = admin_client.get(f"/api/questions/{question['id']}").json()
    legacy = next(item for item in payload["solutions"] if item["image_url"])
    assert legacy["image_url"] == "/media/solutions/legacy.png"
    assert legacy["note"] == "Old style"


def test_a_legacy_solution_opens_in_the_editor_as_its_image(admin_client):
    from app.db import _get_session_factory
    from app.models import Solution

    question = _question(admin_client, "Edit the old photograph")

    async def stash() -> None:
        factory = _get_session_factory()
        async with factory() as session:
            session.add(
                Solution(
                    question_id=question["id"],
                    author_user_id=1,
                    image_path="solutions/legacy.png",
                    note="Old style",
                )
            )
            await session.commit()

    asyncio.run(stash())
    payload = admin_client.get(f"/api/questions/{question['id']}").json()
    assert payload["my_solution"]["body"] == ("![](/media/solutions/legacy.png)\n\nOld style")


def test_saving_a_legacy_solution_does_not_print_its_caption_twice(admin_client):
    """The caption is carried into the prose; leaving it on the row as well made
    the same sentence appear twice under the solution."""
    from app.db import _get_session_factory
    from app.models import Solution

    question = _question(admin_client, "Caption once, please")

    async def stash() -> None:
        factory = _get_session_factory()
        async with factory() as session:
            session.add(
                Solution(
                    question_id=question["id"],
                    author_user_id=1,
                    image_path="solutions/legacy.png",
                    note="Demo caption",
                )
            )
            await session.commit()

    asyncio.run(stash())
    token = admin_client.cookies.get("melereview_csrf")
    saved = admin_client.post(
        f"/api/questions/{question['id']}/solution",
        json={"body": "Demo caption, now as prose."},
        headers={"X-CSRF-Token": token},
    )
    solution = saved.json()["solutions"][0]
    assert solution["note"] is None
    assert solution["body"] == "Demo caption, now as prose."
    assert solution["body_html"].count("Demo caption") == 1
