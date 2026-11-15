"""Tags, search and the admin question list."""

from __future__ import annotations

from app.services.taxonomy import normalise_tag


def _topic(client, index: int = 0) -> int:
    return client.get("/api/subjects").json()[0]["topics"][index]["id"]


def _question(client, topic_id: int, body: str, tags: list[str] | None = None) -> dict:
    response = client.post(
        "/api/questions",
        json={
            "topic_id": topic_id,
            "body": body,
            "choice_a": "one",
            "choice_b": "two",
            "choice_c": "three",
            "choice_d": "four",
            "correct_choice": "B",
            "tags": tags or [],
        },
        headers={"X-CSRF-Token": client.cookies.get("melereview_csrf")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_tag_names_are_normalised():
    assert normalise_tag("Differential Equation") == "differential-equation"
    assert normalise_tag("  Rankine  ") == "rankine"
    assert normalise_tag("fits, tolerance & roughness") == "fits-tolerance-roughness"


def test_a_question_keeps_its_tags(admin_client):
    topic_id = _topic(admin_client)
    created = _question(admin_client, topic_id, "Tagged question", ["derivative", "Steam Tables"])
    assert created["tags"] == ["derivative", "steam-tables"]

    fetched = admin_client.get(f"/api/questions/{created['id']}").json()
    assert fetched["tags"] == ["derivative", "steam-tables"]


def test_tags_cross_topics(admin_client):
    """The point of tags: one label gathers questions from different topics."""
    subjects = admin_client.get("/api/subjects").json()
    first_topic = subjects[0]["topics"][0]["id"]
    other_topic = subjects[1]["topics"][0]["id"]

    a = _question(admin_client, first_topic, "A derivative in calculus", ["derivative"])
    b = _question(admin_client, other_topic, "A derivative in kinematics", ["derivative"])

    found = admin_client.get("/api/search?tags=derivative").json()["results"]
    ids = {item["id"] for item in found}
    assert {a["id"], b["id"]} <= ids


def test_two_tags_narrow_rather_than_widen(admin_client):
    topic_id = _topic(admin_client)
    both = _question(admin_client, topic_id, "Has both tags", ["alpha", "beta"])
    one = _question(admin_client, topic_id, "Has one tag", ["alpha"])

    found = admin_client.get("/api/search?tags=alpha,beta").json()["results"]
    ids = {item["id"] for item in found}
    assert both["id"] in ids
    assert one["id"] not in ids


def test_search_matches_the_statement_and_the_choices(admin_client):
    topic_id = _topic(admin_client)
    statement = _question(admin_client, topic_id, "Compute the Rankine efficiency")
    choice = _question(admin_client, topic_id, "Unrelated wording", [])

    found = admin_client.get("/api/search?q=rankine").json()["results"]
    assert any(item["id"] == statement["id"] for item in found)
    assert all(item["id"] != choice["id"] for item in found)


def test_search_never_returns_an_answer(admin_client):
    topic_id = _topic(admin_client)
    _question(admin_client, topic_id, "Answer must stay hidden")
    payload = admin_client.get("/api/search?q=hidden").json()
    for item in payload["results"]:
        assert "correct_choice" not in item
        assert "answer" not in item


def test_search_suggests_a_matching_tag(admin_client):
    topic_id = _topic(admin_client)
    _question(admin_client, topic_id, "Some wording", ["rankine"])
    payload = admin_client.get("/api/search?q=rankine").json()
    assert "rankine" in payload["suggested_tags"]


def test_the_search_page_renders_and_honours_a_tag(admin_client):
    topic_id = _topic(admin_client)
    created = _question(admin_client, topic_id, "Findable by tag", ["findme"])
    page = admin_client.get("/search?tags=findme")
    assert page.status_code == 200
    assert "Findable by tag" in page.text
    assert created["tags"][0] == "findme"


def test_deleted_questions_leave_the_metrics(admin_client, member_factory):
    """Deleted is stronger than hidden: it stops counting towards the numbers."""
    author = member_factory("deleter")
    solver = member_factory("counted")
    topic_id = _topic(author.client)
    question = _question(author.client, topic_id, "This will be deleted")

    solver.client.post(
        f"/api/questions/{question['id']}/attempt",
        json={"chosen": "B"},
        headers={"X-CSRF-Token": solver.client.cookies.get("melereview_csrf")},
    )
    assert solver.client.get("/api/me/progress").json()["answered"] == 1

    admin_client.post(
        f"/api/admin/questions/{question['id']}/delete",
        headers={"X-CSRF-Token": admin_client.cookies.get("melereview_csrf")},
    )

    progress = solver.client.get("/api/me/progress").json()
    assert progress["answered"] == 0, "a deleted question no longer counts"
    assert progress["solved"] == 0


def test_hidden_questions_still_count(admin_client, member_factory):
    """Hiding keeps the question in the record, so the numbers are unchanged."""
    author = member_factory("hider2")
    solver = member_factory("stillcounts")
    topic_id = _topic(author.client)
    question = _question(author.client, topic_id, "Hidden but counted")
    solver.client.post(
        f"/api/questions/{question['id']}/attempt",
        json={"chosen": "B"},
        headers={"X-CSRF-Token": solver.client.cookies.get("melereview_csrf")},
    )
    admin_client.post(
        f"/api/admin/content/question/{question['id']}/restore",
        headers={"X-CSRF-Token": admin_client.cookies.get("melereview_csrf")},
    )
    assert solver.client.get("/api/me/progress").json()["solved"] == 1


def test_the_admin_question_list_filters_and_sorts(admin_client):
    topic_id = _topic(admin_client)
    low = _question(admin_client, topic_id, "Question for filtering")
    token = admin_client.cookies.get("melereview_csrf")
    admin_client.post(
        f"/api/questions/{low['id']}/vote",
        json={"direction": -1},
        headers={"X-CSRF-Token": token},
    )

    negative = admin_client.get("/api/admin/questions?filter=negative").json()["items"]
    assert any(item["id"] == low["id"] for item in negative)

    deleted = admin_client.get("/api/admin/questions?filter=deleted").json()["items"]
    assert all(item["is_deleted"] for item in deleted)

    by_score = admin_client.get("/api/admin/questions?sort=score").json()["items"]
    scores = [item["score"] for item in by_score]
    assert scores == sorted(scores), "score sorting is ascending, worst first"


def test_the_admin_question_list_searches_live_by_parameter(admin_client):
    topic_id = _topic(admin_client)
    _question(admin_client, topic_id, "Kinematically distinctive wording")
    found = admin_client.get("/api/admin/questions?q=kinematically").json()["items"]
    assert any("Kinematically" in item["body"] for item in found)


def test_only_an_admin_reaches_the_question_list(member_factory):
    member = member_factory("notadmin")
    assert member.client.get("/api/admin/questions").status_code == 403


def test_the_profile_shows_recent_activity(admin_client, member_factory):
    """The strip lives on the profile: what you answered, and what is new."""
    member = member_factory("recentuser")
    topic_id = _topic(member.client)
    question = _question(admin_client, topic_id, "Recently attempted question")
    member.client.post(
        f"/api/questions/{question['id']}/attempt",
        json={"chosen": "A"},
        headers={"X-CSRF-Token": member.client.cookies.get("melereview_csrf")},
    )
    page = member.client.get("/profile")
    assert "Recently answered" in page.text
    assert "Recently added" in page.text
    assert "Recently attempted question" in page.text


def test_the_profile_strip_carries_no_answer(admin_client, member_factory):
    """The strip is a signpost, not a spoiler: no correct letter anywhere in it."""
    member = member_factory("nostripspoiler")
    topic_id = _topic(member.client)
    _question(admin_client, topic_id, "Strip must not spoil")
    page = member.client.get("/profile").text
    assert "correct_choice" not in page


def test_the_library_sorts_topics(admin_client):
    """The library carries a sort control and the data each option needs."""
    page = admin_client.get("/library")
    assert 'id="lib-sort"' in page.text
    for option in ("syllabus", "newest", "questions", "answers", "name"):
        assert f'value="{option}"' in page.text
    assert "data-answers=" in page.text
    assert "data-newest=" in page.text


def test_topics_carry_answer_counts(admin_client, member_factory):
    member = member_factory("counter")
    topic_id = _topic(member.client)
    question = _question(member.client, topic_id, "One answer here")
    member.client.post(
        f"/api/questions/{question['id']}/attempt",
        json={"chosen": "B"},
        headers={"X-CSRF-Token": member.client.cookies.get("melereview_csrf")},
    )
    subjects = member.client.get("/api/subjects").json()
    topics = [topic for subject in subjects for topic in subject["topics"]]
    assert any(topic["answers"] >= 1 for topic in topics)
    assert all("newest" in topic for topic in topics)
