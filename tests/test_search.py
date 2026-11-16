"""Tags, search and the admin question list."""

from __future__ import annotations

from pathlib import Path

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
            "kind": "identification",
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


def test_the_member_strip_carries_no_answer(admin_client, member_factory):
    """The strip is a signpost, not a spoiler: no correct letter anywhere in it."""
    member = member_factory("nostripspoiler")
    topic_id = _topic(member.client)
    _question(admin_client, topic_id, "Strip must not spoil")
    page = member.client.get(f"/users/{member.username}").text
    assert "correct_choice" not in page


def test_the_topic_page_sorts_its_questions(admin_client, member_factory):
    """Sorting belongs on the list of questions, not on the subject index."""
    member = member_factory("sorter")
    topic_id = _topic(member.client)
    first = _question(admin_client, topic_id, "First question here")
    second = _question(admin_client, topic_id, "Second question here")

    newest = member.client.get(f"/api/topics/{topic_id}/questions?sort=newest").json()
    oldest = member.client.get(f"/api/topics/{topic_id}/questions?sort=oldest").json()
    # The topic may already hold questions from other tests, so compare positions
    # rather than assuming these two are the only ones.
    newest_ids = [q["id"] for q in newest]
    oldest_ids = [q["id"] for q in oldest]
    assert newest_ids.index(second["id"]) < newest_ids.index(first["id"])
    assert oldest_ids.index(first["id"]) < oldest_ids.index(second["id"])

    page = member.client.get(f"/topics/{topic_id}")
    assert 'id="q-sort"' in page.text
    for option in ("newest", "oldest", "score", "downvoted", "answered", "unsolved"):
        assert f'value="{option}"' in page.text


def test_the_topic_sort_by_score_puts_the_best_first(admin_client):
    topic_id = _topic(admin_client)
    token = admin_client.cookies.get("melereview_csrf")
    low = _question(admin_client, topic_id, "Score sorting low")
    high = _question(admin_client, topic_id, "Score sorting high")
    admin_client.post(
        f"/api/questions/{high['id']}/vote", json={"direction": 1}, headers={"X-CSRF-Token": token}
    )
    admin_client.post(
        f"/api/questions/{low['id']}/vote", json={"direction": -1}, headers={"X-CSRF-Token": token}
    )

    ordered = admin_client.get(
        f"/api/topics/{topic_id}/questions?sort=score&show_downvoted=true"
    ).json()
    ids = [q["id"] for q in ordered]
    assert ids.index(high["id"]) < ids.index(low["id"])


def test_a_member_page_shows_their_own_activity(admin_client, member_factory):
    """The strips on another member's page are their history and their writing."""
    member = member_factory("activityuser")
    topic_id = _topic(member.client)
    _question(member.client, topic_id, "A question this member wrote")
    other = _question(admin_client, topic_id, "A question somebody else wrote")
    member.client.post(
        f"/api/questions/{other['id']}/attempt",
        json={"chosen": "A"},
        headers={"X-CSRF-Token": member.client.cookies.get("melereview_csrf")},
    )

    page = admin_client.get(f"/users/{member.username}")
    assert page.status_code == 200
    assert "Recently answered" in page.text
    assert "Recently added" in page.text
    assert "A question this member wrote" in page.text, "their own question is listed"
    assert "A question somebody else wrote" in page.text, "what they answered is listed"


def test_a_member_page_lists_only_their_questions(admin_client, member_factory):
    one = member_factory("firstauthor")
    two = member_factory("secondauthor")
    topic_id = _topic(one.client)
    _question(one.client, topic_id, "Written by the first author")
    _question(two.client, topic_id, "Written by the second author")

    page = admin_client.get(f"/users/{one.username}").text
    added = page.split('data-strip-panel="authored"')[1].split("</section>")[0]
    assert "Written by the first author" in added
    assert "Written by the second author" not in added


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


def test_a_card_carries_its_tags(admin_client):
    """The card is where a question is read, so the tags have to be on it."""
    topic_id = _topic(admin_client)
    created = _question(admin_client, topic_id, "Tagged at the card", ["derivative", "steam"])

    listing = admin_client.get(f"/api/topics/{topic_id}/questions").json()
    card = next(item for item in listing if item["id"] == created["id"])
    assert card["tags"] == ["derivative", "steam"]

    source = (Path("app/static/js/card.js")).read_text()
    assert "question.tags" in source, "the card renders the tags it is given"
    assert "/tags/" in source, "each tag links to its own page"


def test_a_question_can_carry_a_tag_nobody_has_used(admin_client):
    topic_id = _topic(admin_client)
    created = _question(admin_client, topic_id, "Brand new idea", ["never-used-before"])
    assert created["tags"] == ["never-used-before"]

    page = admin_client.get("/tags/never-used-before")
    assert page.status_code == 200
    assert "Brand new idea" in page.text


def test_questions_without_tags_are_fine(admin_client):
    topic_id = _topic(admin_client)
    created = _question(admin_client, topic_id, "No tags at all")
    assert created["tags"] == []
    listing = admin_client.get(f"/api/topics/{topic_id}/questions").json()
    card = next(item for item in listing if item["id"] == created["id"])
    assert card["tags"] == []


def test_the_tag_page_gathers_one_tag_across_topics(admin_client):
    subjects = admin_client.get("/api/subjects").json()
    first = _question(
        admin_client, subjects[0]["topics"][1]["id"], "Calculus side", ["shared-idea"]
    )
    second = _question(admin_client, subjects[1]["topics"][1]["id"], "Plant side", ["shared-idea"])

    page = admin_client.get("/tags/shared-idea")
    assert page.status_code == 200
    assert "Calculus side" in page.text
    assert "Plant side" in page.text
    assert first["id"] != second["id"]


def test_the_tag_index_lists_every_tag_in_use(admin_client):
    topic_id = _topic(admin_client)
    _question(admin_client, topic_id, "Indexed", ["indexed-tag"])
    page = admin_client.get("/tags")
    assert page.status_code == 200
    assert "indexed-tag" in page.text


def test_the_edit_link_appears_only_for_the_author_or_a_moderator(admin_client, member_factory):
    author = member_factory("editor")
    bystander = member_factory("nottheauthor")
    topic_id = _topic(author.client)
    created = _question(author.client, topic_id, "Who may edit this")

    own = author.client.get(f"/api/questions/{created['id']}").json()
    assert own["can_edit"] is True

    theirs = bystander.client.get(f"/api/questions/{created['id']}").json()
    assert theirs["can_edit"] is False

    admin = admin_client.get(f"/api/questions/{created['id']}").json()
    assert admin["can_edit"] is True, "the system administrator and moderators may edit"

    source = (Path("app/static/js/card.js")).read_text()
    assert "can_edit" in source, "the card renders the edit link from this flag"
    assert "/edit" in source
    assert "options.detail" in source, "the edit control belongs on the question page"
    detail = (Path("app/static/js/question.js")).read_text()
    assert "detail: true" in detail, "the question page is the detail view"
    listing = (Path("app/static/js/topic.js")).read_text()
    assert "detail: true" not in listing, "a list must not offer editing"


def test_a_bystander_cannot_edit_through_the_api(admin_client, member_factory):
    author = member_factory("apiowner")
    bystander = member_factory("apiintruder")
    topic_id = _topic(author.client)
    created = _question(author.client, topic_id, "Editing is guarded")

    response = bystander.client.put(
        f"/api/questions/{created['id']}",
        json={
            "topic_id": topic_id,
            "body": "hijacked",
            "choice_a": "a",
            "choice_b": "b",
            "choice_c": "c",
            "choice_d": "d",
            "correct_choice": "A",
            "kind": "identification",
        },
        headers={"X-CSRF-Token": bystander.client.cookies.get("melereview_csrf")},
    )
    assert response.status_code == 403


def test_the_edit_page_opens_for_the_author_and_refuses_a_bystander(admin_client, member_factory):
    author = member_factory("pageowner")
    bystander = member_factory("pageintruder")
    topic_id = _topic(author.client)
    created = _question(author.client, topic_id, "Edit page access")

    own = author.client.get(f"/questions/{created['id']}/edit")
    assert own.status_code == 200
    assert 'id="f-tags"' in own.text, "the edit page carries the tag picker"

    theirs = bystander.client.get(f"/questions/{created['id']}/edit")
    assert theirs.status_code == 403


def test_the_edit_page_prefills_the_existing_tags(admin_client):
    """An edit form that starts empty would silently drop the tags on save."""
    topic_id = _topic(admin_client)
    created = _question(admin_client, topic_id, "Prefill check", ["alpha", "beta"])
    page = admin_client.get(f"/questions/{created['id']}/edit")
    assert page.status_code == 200
    assert 'data-selected="alpha,beta"' in page.text


def test_a_result_card_does_not_nest_anchors():
    """Tag pills are anchors, so the card cannot itself be one: the browser drops
    an anchor inside an anchor, and the pills vanish without an error."""
    for name in ("app/templates/tag.html", "app/templates/search.html"):
        source = Path(name).read_text()
        assert '<a class="result"' not in source, f"{name} nests anchors"
        assert 'class="result__main"' in source, f"{name} needs a link inside the card"
