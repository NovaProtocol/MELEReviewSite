"""The Markdown editor, uploads, and the filters on the topic list."""

from __future__ import annotations

from conftest import PNG_BYTES


def _topic_id(client) -> int:
    return client.get("/api/subjects").json()[0]["topics"][0]["id"]


def _question(client, body: str = "A question with markup", **extra) -> dict:
    token = client.cookies.get("melereview_csrf")
    payload = {
        "topic_id": _topic_id(client),
        "body": body,
        "choice_a": "one",
        "choice_b": "two",
        "choice_c": "three",
        "choice_d": "four",
        "correct_choice": "A",
        **extra,
    }
    response = client.post("/api/questions", json=payload, headers={"X-CSRF-Token": token})
    assert response.status_code == 201, response.text
    return response.json()


def _upload(client, name: str = "shot.png", raw: bytes = PNG_BYTES) -> dict:
    token = client.cookies.get("melereview_csrf")
    response = client.post(
        "/api/media",
        files={"file": (name, raw, "image/png")},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_markdown_renders_the_subset_the_editor_offers(admin_client):
    token = admin_client.cookies.get("melereview_csrf")
    source = "**bold** *italic* ~~gone~~ ^2^ `code`\n\n- one\n- two\n\n> a quote"
    response = admin_client.post(
        "/api/editor/preview",
        json={"markdown": source},
        headers={"X-CSRF-Token": token},
    )
    html = response.json()["html"]
    assert "<strong>bold</strong>" in html
    assert "<em>italic</em>" in html
    assert "<del>gone</del>" in html
    assert "<sup>2</sup>" in html
    assert "<code>code</code>" in html
    assert "<li>one</li>" in html
    assert "<blockquote>a quote</blockquote>" in html


def test_markdown_never_lets_authors_inject_html(admin_client):
    token = admin_client.cookies.get("melereview_csrf")
    for source in (
        "<script>alert(1)</script>",
        '<img src=x onerror="alert(1)">',
        "[click](javascript:alert(1))",
    ):
        html = admin_client.post(
            "/api/editor/preview",
            json={"markdown": source},
            headers={"X-CSRF-Token": token},
        ).json()["html"]
        # The text may survive as text; what must not survive is a live tag or a
        # link that runs script.
        assert "<script" not in html
        assert "<img src=x" not in html
        assert 'href="javascript:' not in html


def test_an_upload_can_be_referenced_by_uid_and_survives_a_domain_change(admin_client):
    media = _upload(admin_client)
    assert media["url"] == f"/media/{media['uid']}"
    assert media["markdown"] == f"![](/media/{media['uid']})"
    assert media["width"] == 1 and media["height"] == 1

    served = admin_client.get(media["url"])
    assert served.status_code == 200
    assert served.content == PNG_BYTES

    info = admin_client.get(f"/api/media/{media['uid']}/info").json()
    assert info["byte_size"] == len(PNG_BYTES)
    assert info["question_id"] is None, "not used by a question yet"


def test_an_upload_records_the_question_that_uses_it(admin_client):
    media = _upload(admin_client)
    question = _question(admin_client, f"See the diagram\n\n![work](/media/{media['uid']})")

    info = admin_client.get(f"/api/media/{media['uid']}/info").json()
    assert info["question_id"] == question["id"]

    # An edit that drops the image releases it, so "where is this used" stays true.
    token = admin_client.cookies.get("melereview_csrf")
    admin_client.put(
        f"/api/questions/{question['id']}",
        json={
            "topic_id": _topic_id(admin_client),
            "body": "No image any more",
            "choice_a": "one",
            "choice_b": "two",
            "choice_c": "three",
            "choice_d": "four",
            "correct_choice": "A",
        },
        headers={"X-CSRF-Token": token},
    )
    assert admin_client.get(f"/api/media/{media['uid']}/info").json()["question_id"] is None


def test_an_oversized_upload_is_refused(admin_client, monkeypatch):
    from app.config import get_config

    config = get_config()
    monkeypatch.setattr(config, "MAX_MEDIA_BYTES", 16)
    token = admin_client.cookies.get("melereview_csrf")
    response = admin_client.post(
        "/api/media",
        files={"file": ("big.png", PNG_BYTES, "image/png")},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 413


def test_the_question_payload_carries_rendered_html(admin_client):
    question = _question(admin_client, "**Bold** statement")
    assert "<strong>Bold</strong>" in question["body_html"]


def test_the_note_is_rendered_too(admin_client):
    question = _question(admin_client, "Plain", explanation="Use **9.81** for g")
    assert "<strong>9.81</strong>" in question["note_html"]


# --- topic list filters -------------------------------------------------


def _solve(client, question: dict) -> None:
    token = client.cookies.get("melereview_csrf")
    client.post(
        f"/api/questions/{question['id']}/attempt",
        json={"chosen": "A"},
        headers={"X-CSRF-Token": token},
    )


def _list(client, **params) -> list[dict]:
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return client.get(f"/api/topics/{_topic_id(client)}/questions?{query}").json()


def _by_id(items: list[dict]) -> dict[int, dict]:
    return {item["id"]: item for item in items}


def test_the_answer_filter_asks_the_viewers_own_sheet(admin_client):
    answered = _question(admin_client, "I have answered this")
    _question(admin_client, "I have not answered this")
    _solve(admin_client, answered)

    ids = _by_id(_list(admin_client, answer_state="answered"))
    assert answered["id"] in ids
    assert all(item["attempt"] for item in ids.values())

    rest = _by_id(_list(admin_client, answer_state="unanswered"))
    assert answered["id"] not in rest
    assert all(not item["attempt"] for item in rest.values())

    assert len(_list(admin_client)) >= len(ids)


def test_the_solution_filter_finds_questions_with_working(admin_client):
    with_working = _question(admin_client, "Somebody posted working")
    _question(admin_client, "Nobody posted working")
    token = admin_client.cookies.get("melereview_csrf")
    admin_client.post(
        f"/api/questions/{with_working['id']}/solution",
        files={"file": ("worked.png", PNG_BYTES, "image/png")},
        headers={"X-CSRF-Token": token},
    )

    found = _by_id(_list(admin_client, has_solution="true"))
    assert with_working["id"] in found
    assert all(item["solution_count"] >= 1 for item in found.values())


def test_the_mine_filter_keeps_only_your_own(admin_client, member_factory):
    theirs = _question(admin_client, "Written by the administrator")
    member = member_factory("filterowner")
    _question(member.client, "Written by the member")

    mine = _by_id(_list(member.client, mine="true"))
    assert theirs["id"] not in mine
    assert mine, "the member wrote one question"


def test_filters_combine_rather_than_replace(admin_client):
    """Starred and unanswered at once is a valid request, so both must apply."""
    starred_unanswered = _question(admin_client, "Starred and unanswered")
    starred_answered = _question(admin_client, "Starred and answered")
    token = admin_client.cookies.get("melereview_csrf")
    for question in (starred_unanswered, starred_answered):
        admin_client.post(
            f"/api/questions/{question['id']}/favourite",
            headers={"X-CSRF-Token": token},
        )
    _solve(admin_client, starred_answered)

    both = _by_id(_list(admin_client, favourites="true", answer_state="unanswered"))
    assert starred_unanswered["id"] in both
    assert starred_answered["id"] not in both


def test_a_list_card_never_replays_the_answer(admin_client):
    """The list shows the question and its choices. What was answered is the
    badge, not a marked choice."""
    from pathlib import Path

    source = Path("app/static/js/card.js").read_text()
    assert "if (question.attempt) reveal(question.attempt);" in source
    # The reveal call must sit after the read-only return, or a list card would
    # mark a choice as wrong before it stops.
    read_only = source.index("if (!options.interactive)")
    reveal = source.index("if (question.attempt) reveal(question.attempt);")
    assert reveal > read_only, "a list card must not reveal the previous attempt"

    assert 'textContent = "ANSWERED"' in source
    assert "!options.detail && question.attempt" in source


def test_no_script_closes_its_wrapper_twice():
    """A page script is wrapped in one IIFE. Closing it twice leaves the last
    statement of the DOMContentLoaded handler being *called* instead of a plain
    close, which throws at runtime while everything before it has already run."""
    from pathlib import Path

    for path in Path("app/static/js").glob("*.js"):
        lines = [line.strip() for line in path.read_text().splitlines()]
        for index in range(len(lines) - 1):
            assert not (lines[index] == "})();" and lines[index + 1] == "})();"), (
                f"{path} closes its wrapper twice near line {index + 1}"
            )
