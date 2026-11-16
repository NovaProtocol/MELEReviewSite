"""Crossing choices out: a note to yourself on a question, kept per member."""

from __future__ import annotations


def _topic_id(client) -> int:
    return client.get("/api/subjects").json()[0]["topics"][0]["id"]


def _question(client, body: str = "Which choice is ruled out?") -> dict:
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
            "kind": "identification",
        },
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _strike(client, question_id: int, letter: str, value: int):
    token = client.cookies.get("melereview_csrf")
    return client.post(
        f"/api/questions/{question_id}/strike",
        json={"letter": letter, "value": value},
        headers={"X-CSRF-Token": token},
    )


def test_a_choice_can_be_crossed_out_and_put_back(admin_client):
    question = _question(admin_client)
    assert _strike(admin_client, question["id"], "C", 1).json()["struck"] == "C"
    assert _strike(admin_client, question["id"], "B", 1).json()["struck"] == "BC"
    assert _strike(admin_client, question["id"], "C", 0).json()["struck"] == "B"
    assert _strike(admin_client, question["id"], "B", 0).json()["struck"] == ""


def test_the_marking_rides_on_the_question_payload(admin_client):
    question = _question(admin_client)
    _strike(admin_client, question["id"], "D", 1)
    detail = admin_client.get(f"/api/questions/{question['id']}").json()
    assert detail["struck"] == "D"


def test_markings_are_per_member(admin_client, member_factory):
    question = _question(admin_client)
    _strike(admin_client, question["id"], "A", 1)

    member = member_factory("strikemember")
    detail = member.client.get(f"/api/questions/{question['id']}").json()
    assert detail["struck"] == "", "one member's crossings are not another's"

    _strike(member.client, question["id"], "B", 1)
    assert admin_client.get(f"/api/questions/{question['id']}").json()["struck"] == "A"


def test_crossing_out_is_not_an_answer(admin_client):
    question = _question(admin_client)
    _strike(admin_client, question["id"], "B", 1)
    detail = admin_client.get(f"/api/questions/{question['id']}").json()
    assert detail["attempt"] is None, "a marking must not count as an attempt"


def test_a_nonsense_letter_is_refused(admin_client):
    question = _question(admin_client)
    assert _strike(admin_client, question["id"], "Z", 1).status_code == 422
