"""Quiz mode: building a paper, its code, the random draw, and scoring."""

from __future__ import annotations


def _topic_id(client, index: int = 0) -> int:
    return client.get("/api/subjects").json()[0]["topics"][index]["id"]


def _question(client, topic_id: int, body: str, tags: list[str] | None = None) -> dict:
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
            "tags": tags or [],
        },
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _build(client, selections: dict, **settings) -> dict:
    token = client.cookies.get("melereview_csrf")
    payload = {"selections": selections, "timer_minutes": 30, "group": "mixed", **settings}
    response = client.post("/api/quiz/build", json=payload, headers={"X-CSRF-Token": token})
    assert response.status_code == 200, response.text
    return response.json()


def _solve(client, question_id: int, letter: str = "A") -> None:
    token = client.cookies.get("melereview_csrf")
    client.post(
        f"/api/questions/{question_id}/attempt",
        json={"chosen": letter},
        headers={"X-CSRF-Token": token},
    )


def test_a_quiz_is_built_from_the_chosen_topics(admin_client):
    topic = _topic_id(admin_client)
    made = [_question(admin_client, topic, f"Quiz question {index}") for index in range(5)]

    built = _build(admin_client, {str(topic): 3})
    assert len(built["questions"]) == 3
    ids = [item["id"] for item in built["questions"]]
    assert len(set(ids)) == 3, "a quiz never repeats a question"
    assert built["code"]
    # Every pick comes from the topic that was asked for. (The bank is shared with
    # the rest of the run, so the ids are checked rather than the specific rows.)
    for question_id in ids:
        assert admin_client.get(f"/api/questions/{question_id}").json()["topic_id"] == topic
    assert made


def test_the_code_carries_the_same_paper(admin_client):
    topic = _topic_id(admin_client)
    for index in range(4):
        _question(admin_client, topic, f"Code question {index}")
    built = _build(admin_client, {str(topic): 4})

    reopened = admin_client.get(f"/api/quiz/{built['code']}").json()
    assert [item["id"] for item in reopened["questions"]] == [
        item["id"] for item in built["questions"]
    ], "the order is part of the code"
    assert reopened["settings"]["timer_minutes"] == 30


def test_the_quiz_page_renders_the_bank(admin_client):
    page = admin_client.get("/quiz")
    assert page.status_code == 200
    assert "Question bank" in page.text
    assert 'id="quiz-start"' in page.text


def test_an_unreadable_code_is_refused(admin_client):
    assert admin_client.get("/api/quiz/not-a-real-code").status_code == 422
    token = admin_client.cookies.get("melereview_csrf")
    assert (
        admin_client.post(
            "/api/quiz/submit",
            json={"code": "garbage", "answers": {"1": "A"}},
            headers={"X-CSRF-Token": token},
        ).status_code
        == 422
    )


def test_grouping_by_topic_keeps_topics_together(admin_client):
    subjects = admin_client.get("/api/subjects").json()
    first = subjects[0]["topics"][0]["id"]
    second = subjects[0]["topics"][1]["id"]
    for index in range(3):
        _question(admin_client, first, f"Group A {index}")
        _question(admin_client, second, f"Group B {index}")

    built = _build(admin_client, {str(first): 3, str(second): 3}, group="topic")
    topics = [item["topic_id"] for item in built["questions"]]
    # Each topic appears as one contiguous run.
    for topic in {first, second}:
        positions = [index for index, value in enumerate(topics) if value == topic]
        assert positions == list(range(positions[0], positions[0] + len(positions)))


def test_a_filter_leaves_out_the_computation_tag(admin_client):
    topic = _topic_id(admin_client)
    _question(admin_client, topic, "Plain question", ["algebra"])
    _question(admin_client, topic, "Compute the value", ["computation"])

    built = _build(
        admin_client,
        {str(topic): 10},
        filters={"exclude_computation": True},
    )
    bodies = [item["body"] for item in built["questions"]]
    assert bodies
    assert all("Compute the value" not in body for body in bodies)


def test_only_unanswered_can_be_asked_for(admin_client):
    topic = _topic_id(admin_client)
    answered = _question(admin_client, topic, "Already answered")
    _question(admin_client, topic, "Still unanswered")
    _solve(admin_client, answered["id"])

    built = _build(admin_client, {str(topic): 10}, filters={"unanswered_only": True})
    assert all(item["id"] != answered["id"] for item in built["questions"])


def test_a_quiz_with_nothing_selected_is_refused(admin_client):
    token = admin_client.cookies.get("melereview_csrf")
    response = admin_client.post(
        "/api/quiz/build",
        json={"selections": {}, "timer_minutes": 30},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 422


def test_submitting_scores_and_records_attempts(admin_client):
    topic = _topic_id(admin_client)
    _question(admin_client, topic, "I know this one")
    _question(admin_client, topic, "I do not know this one")
    # The whole topic, so the paper is predictable whatever else the tests left.
    built = _build(admin_client, {str(topic): 200})
    picked = built["questions"][:2]

    answers = {str(picked[0]["id"]): picked[0]["correct_choice"]}
    answers[str(picked[1]["id"])] = next(
        letter
        for letter in ("A", "B", "C", "D")
        if picked[1]["choices"].get(letter) and letter != picked[1]["correct_choice"]
    )

    token = admin_client.cookies.get("melereview_csrf")
    result = admin_client.post(
        "/api/quiz/submit",
        json={"code": built["code"], "answers": answers},
        headers={"X-CSRF-Token": token},
    ).json()

    assert result["total"] == 2
    assert result["correct"] == 1
    assert result["score"] == 50
    assert picked[1]["id"] in [item["question_id"] for item in result["results"]]

    # The answers are ordinary attempts, so the profile moves with them.
    me = admin_client.get("/api/auth/me").json()
    assert me["progress"]["answered"] >= 2


def test_a_quiz_does_not_re_answer_a_solved_question(admin_client):
    topic = _topic_id(admin_client)
    question = _question(admin_client, topic, "Solved before the quiz")
    _solve(admin_client, question["id"], "A")

    built = _build(admin_client, {str(topic): 200})
    assert question["id"] in [item["id"] for item in built["questions"]]
    token = admin_client.cookies.get("melereview_csrf")
    result = admin_client.post(
        "/api/quiz/submit",
        json={"code": built["code"], "answers": {str(question["id"]): "D"}},
        headers={"X-CSRF-Token": token},
    ).json()
    entry = result["results"][0]
    assert entry["status"] == "already solved"
    assert entry["correct"] is True


def test_random_mode_returns_a_question_and_honours_the_filters(admin_client):
    topic = _topic_id(admin_client)
    _question(admin_client, topic, "Random candidate", ["algebra"])
    _question(admin_client, topic, "Random computation", ["computation"])

    token = admin_client.cookies.get("melereview_csrf")
    for _ in range(6):
        found = admin_client.post(
            "/api/quiz/random",
            json={"exclude_computation": True},
            headers={"X-CSRF-Token": token},
        )
        assert found.status_code == 200
        detail = admin_client.get(f"/api/questions/{found.json()['question_id']}").json()
        assert "Random computation" not in detail["body"]


def test_random_mode_can_skip_a_topic(admin_client):
    subjects = admin_client.get("/api/subjects").json()
    hidden = subjects[0]["topics"][0]["id"]
    _question(admin_client, hidden, "Never picked")
    _question(admin_client, subjects[0]["topics"][1]["id"], "Only candidate", ["algebra"])

    token = admin_client.cookies.get("melereview_csrf")
    for _ in range(6):
        found = admin_client.post(
            "/api/quiz/random",
            json={"exclude_topics": [hidden]},
            headers={"X-CSRF-Token": token},
        ).json()
        assert found["topic_id"] != hidden
