"""Quiz mode: building a saved paper, sitting it, and what survives."""

from __future__ import annotations


def _topic_id(client, index: int = 0) -> int:
    return client.get("/api/subjects").json()[0]["topics"][index]["id"]


def _question(
    client, topic_id: int, body: str, tags: list[str] | None = None, kind: str = "identification"
) -> dict:
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
            "kind": kind,
            "tags": tags or [],
        },
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create(client, selections: dict, **extra) -> dict:
    token = client.cookies.get("melereview_csrf")
    payload = {
        "selections": selections,
        "timer_minutes": 30,
        "group": "mixed",
        "title": "Test paper",
        **extra,
    }
    response = client.post("/api/quizzes", json=payload, headers={"X-CSRF-Token": token})
    assert response.status_code == 201, response.text
    return response.json()


def _start(client, uid: str, practice: bool = False):
    token = client.cookies.get("melereview_csrf")
    return client.post(
        f"/api/quizzes/{uid}/start",
        json={"practice": practice},
        headers={"X-CSRF-Token": token},
    )


def _submit(client, uid: str, answers: dict, practice: bool = False):
    token = client.cookies.get("melereview_csrf")
    return client.post(
        f"/api/quizzes/{uid}/submit",
        json={"answers": answers, "practice": practice},
        headers={"X-CSRF-Token": token},
    )


def _payload(client, uid: str) -> dict:
    return client.get(f"/api/quizzes/{uid}").json()


def test_a_quiz_is_saved_with_its_questions(admin_client):
    topic = _topic_id(admin_client)
    for index in range(4):
        _question(admin_client, topic, f"Saved paper {index}")

    created = _create(admin_client, {str(topic): 4})
    assert created["uid"]
    page = admin_client.get(f"/quiz/{created['uid']}")
    assert page.status_code == 200

    payload = _payload(admin_client, created["uid"])
    assert len(payload["questions"]) == 4
    assert payload["title"] == "Test paper"
    assert payload["owner"] == "admin"


def test_the_quiz_list_shows_a_public_quiz(admin_client, member_factory):
    topic = _topic_id(admin_client)
    _question(admin_client, topic, "Listed paper")
    uid = _create(admin_client, {str(topic): 1})["uid"]

    member = member_factory("quizreader")
    listing = member.client.get("/api/quizzes").json()["quizzes"]
    assert any(item["uid"] == uid for item in listing)
    assert member.client.get(f"/quiz/{uid}").status_code == 200


def test_an_unlisted_quiz_is_reachable_by_link_but_not_listed(admin_client, member_factory):
    topic = _topic_id(admin_client)
    _question(admin_client, topic, "Unlisted paper")
    uid = _create(admin_client, {str(topic): 1}, is_private=True)["uid"]

    member = member_factory("quizoutsider")
    listing = member.client.get("/api/quizzes").json()["quizzes"]
    assert all(item["uid"] != uid for item in listing)
    assert member.client.get(f"/quiz/{uid}").status_code == 200, "the link still works"

    admin_listing = admin_client.get("/api/quizzes").json()["quizzes"]
    assert any(item["uid"] == uid for item in admin_listing)


def test_a_sitting_is_scored_and_the_first_take_is_kept(admin_client):
    topic = _topic_id(admin_client)
    _question(admin_client, topic, "First take question")
    # The whole topic: the bank is shared with the rest of the run, so a paper of
    # one could pick somebody else's question and a different answer key.
    uid = _create(admin_client, {str(topic): 200})["uid"]
    question = _payload(admin_client, uid)["questions"][0]

    assert _start(admin_client, uid).status_code == 200
    first = _submit(admin_client, uid, {str(question["id"]): "A"})
    assert first.status_code == 200
    kept = first.json()["score"]
    assert 0 <= kept <= 100
    assert first.json()["is_first_take"] is True

    assert _submit(admin_client, uid, {str(question["id"]): "B"}).status_code == 409
    assert _payload(admin_client, uid)["my_first"]["score"] == kept


def test_opening_again_shows_the_first_take(admin_client):
    topic = _topic_id(admin_client)
    _question(admin_client, topic, "Reopen question")
    uid = _create(admin_client, {str(topic): 200})["uid"]
    question = _payload(admin_client, uid)["questions"][0]
    _start(admin_client, uid)
    _submit(admin_client, uid, {str(question["id"]): "A"})

    assert _start(admin_client, uid).status_code == 409
    payload = _payload(admin_client, uid)
    assert payload["my_first"]["submitted"] is True
    assert payload["my_first"]["score"] is not None


def test_a_practice_run_does_not_replace_the_score(admin_client):
    topic = _topic_id(admin_client)
    _question(admin_client, topic, "Practice question")
    uid = _create(admin_client, {str(topic): 200})["uid"]
    question = _payload(admin_client, uid)["questions"][0]

    _start(admin_client, uid)
    first = _submit(admin_client, uid, {str(question["id"]): "A"}).json()

    assert _start(admin_client, uid, practice=True).status_code == 200
    practice = _submit(admin_client, uid, {str(question["id"]): "B"}, practice=True)
    assert practice.status_code == 200
    assert practice.json()["is_first_take"] is False

    assert _payload(admin_client, uid)["my_first"]["score"] == first["score"]


def test_the_owner_sees_who_sat_it(admin_client, member_factory):
    topic = _topic_id(admin_client)
    _question(admin_client, topic, "Sitting question")
    uid = _create(admin_client, {str(topic): 1})["uid"]
    question = _payload(admin_client, uid)["questions"][0]

    member = member_factory("quizsitter")
    _start(member.client, uid)
    _submit(member.client, uid, {str(question["id"]): "A"})

    payload = _payload(admin_client, uid)
    assert [row["user"] for row in payload["submissions"]] == [member.username]
    assert any(row["user"] == member.username for row in payload["leaderboard"])

    other = member_factory("quizobserver")
    assert _payload(other.client, uid)["submissions"] == []


def test_deleting_a_quiz_destroys_its_sittings(admin_client, member_factory):
    topic = _topic_id(admin_client)
    _question(admin_client, topic, "Doomed paper")
    uid = _create(admin_client, {str(topic): 1})["uid"]
    question = _payload(admin_client, uid)["questions"][0]

    member = member_factory("doomedtaker")
    _start(member.client, uid)
    _submit(member.client, uid, {str(question["id"]): "A"})

    token = admin_client.cookies.get("melereview_csrf")
    deleted = admin_client.delete(f"/api/quizzes/{uid}", headers={"X-CSRF-Token": token})
    assert deleted.status_code == 204
    assert admin_client.get(f"/quiz/{uid}").status_code == 404
    assert member.client.get(f"/quiz/{uid}").status_code == 404


def test_a_member_cannot_delete_someone_elses_quiz(admin_client, member_factory):
    topic = _topic_id(admin_client)
    _question(admin_client, topic, "Not yours")
    uid = _create(admin_client, {str(topic): 1})["uid"]

    member = member_factory("quizdeleter")
    token = member.client.cookies.get("melereview_csrf")
    response = member.client.delete(f"/api/quizzes/{uid}", headers={"X-CSRF-Token": token})
    assert response.status_code == 403


def test_retiring_a_question_locks_the_quiz(admin_client):
    topic = _topic_id(admin_client)
    question = _question(admin_client, topic, "Retired paper question")
    # The whole topic, so the paper is certain to contain the question about to be
    # retired. The test database is shared across the run.
    uid = _create(admin_client, {str(topic): 200})["uid"]

    token = admin_client.cookies.get("melereview_csrf")
    admin_client.post(
        f"/api/admin/questions/{question['id']}/delete", headers={"X-CSRF-Token": token}
    )

    payload = _payload(admin_client, uid)
    assert payload["locked"], "a paper with a retired question is closed"
    assert question["id"] in [item["id"] for item in payload["questions"]], (
        "the paper still shows it"
    )
    assert _start(admin_client, uid).status_code == 409


def test_a_private_scores_quiz_hides_the_board(admin_client, member_factory):
    topic = _topic_id(admin_client)
    _question(admin_client, topic, "Quiet board")
    uid = _create(admin_client, {str(topic): 1}, scores_public=False)["uid"]
    question = _payload(admin_client, uid)["questions"][0]

    member = member_factory("quiettaker")
    _start(member.client, uid)
    _submit(member.client, uid, {str(question["id"]): "A"})

    assert _payload(member.client, uid)["leaderboard"] == []
    assert _payload(admin_client, uid)["leaderboard"], "the owner still sees it"


def test_building_needs_a_topic_and_questions(admin_client):
    token = admin_client.cookies.get("melereview_csrf")
    empty = admin_client.post(
        "/api/quizzes",
        json={"selections": {}, "title": "Nothing", "timer_minutes": 30},
        headers={"X-CSRF-Token": token},
    )
    assert empty.status_code == 422


def test_the_quiz_kind_filter_reaches_the_saved_paper(admin_client):
    topic = _topic_id(admin_client)
    _question(admin_client, topic, "Computing paper question", kind="computation")
    _question(admin_client, topic, "Naming paper question", kind="identification")
    uid = _create(admin_client, {str(topic): 50}, filters={"kind": "computation"})["uid"]
    questions = _payload(admin_client, uid)["questions"]
    assert questions
    assert all(item["kind"] == "computation" for item in questions)


def test_random_mode_and_the_bank_filters(admin_client):
    topic = _topic_id(admin_client)
    _question(admin_client, topic, "Random candidate")
    token = admin_client.cookies.get("melereview_csrf")
    found = admin_client.post(
        "/api/quiz/random", json={"kind": "identification"}, headers={"X-CSRF-Token": token}
    )
    assert found.status_code == 200
    assert found.json()["question_id"]
