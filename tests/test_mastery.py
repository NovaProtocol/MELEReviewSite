"""The topic breakdown on a member page, and the switch that hides it."""

from __future__ import annotations


def _topic_id(client, index: int = 0) -> int:
    return client.get("/api/subjects").json()[0]["topics"][index]["id"]


def _question(client, topic_id: int, body: str) -> dict:
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
            "kind": "identification",
        },
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _solve(client, question_id: int, letter: str = "A") -> None:
    token = client.cookies.get("melereview_csrf")
    client.post(
        f"/api/questions/{question_id}/attempt",
        json={"chosen": letter},
        headers={"X-CSRF-Token": token},
    )


def test_the_profile_shows_tried_topics_only(admin_client, member_factory):
    member = member_factory("masterymember")
    uid = member.client.get("/api/auth/me").json()["uid"]
    question = _question(admin_client, _topic_id(admin_client), "A topic I have tried")
    _solve(member.client, question["id"], "A")

    page = member.client.get(f"/users/{uid}")
    assert page.status_code == 200
    assert 'id="root"' in page.text
    progress = member.client.get("/api/auth/me").json()["progress"]
    assert progress["by_subject"], "a tried topic must appear in the breakdown"


def test_a_private_breakdown_is_hidden_from_others(admin_client, member_factory):
    member = member_factory("privatemember")
    uid = member.client.get("/api/auth/me").json()["uid"]
    question = _question(admin_client, _topic_id(admin_client), "Private attempt")
    _solve(member.client, question["id"], "A")

    token = member.client.cookies.get("melereview_csrf")
    saved = member.client.put(
        f"/api/users/{uid}/privacy",
        json={"progress_private": True},
        headers={"X-CSRF-Token": token},
    )
    assert saved.status_code == 200
    assert saved.json()["progress_private"] is True

    own = member.client.get(f"/api/users/{uid}").json()
    assert own["show_breakdown"] is True, "you always see your own"
    assert own["mastery"], "your own breakdown is present"

    observer = member_factory("privacyobserver")
    other = observer.client.get(f"/api/users/{uid}").json()
    assert other["show_breakdown"] is False
    assert other["mastery"] is None
    assert other["breakdown_hidden_message"]

    # Hidden means hidden: the administrator browsing profiles sees the same.
    assert admin_client.get(f"/api/users/{uid}").json()["mastery"] is None


def test_the_breakdown_is_public_unless_turned_off(admin_client, member_factory):
    member = member_factory("publicmember")
    uid = member.client.get("/api/auth/me").json()["uid"]
    question = _question(admin_client, _topic_id(admin_client), "Public attempt")
    _solve(member.client, question["id"], "A")

    view = admin_client.get(f"/api/users/{uid}").json()
    assert view["show_breakdown"] is True
    assert view["mastery"], "a public breakdown is present"


def test_the_breakdown_counts_solved_and_first_tries(admin_client, member_factory):
    member = member_factory("countmember")
    uid = member.client.get("/api/auth/me").json()["uid"]
    topic = _topic_id(admin_client)
    first = _question(admin_client, topic, "Solved first go")
    second = _question(admin_client, topic, "Solved on the second go")
    _solve(member.client, first["id"], "A")
    _solve(member.client, second["id"], "C")
    _solve(member.client, second["id"], "A")

    view = member.client.get(f"/api/users/{uid}").json()
    rows = view["mastery"]
    assert rows, "the breakdown must carry the topic"
    # Two answered, both solved, one of them first try.
    row = max(rows, key=lambda item: item["answered"])
    assert row["answered"] == 2
    assert row["solved"] == 2
    assert row["first_correct"] == 1


def test_the_privacy_switch_needs_to_be_yours(admin_client, member_factory):
    owner = member_factory("privacyowner")
    intruder = member_factory("privacyintruder")
    uid = owner.client.get("/api/auth/me").json()["uid"]
    token = intruder.client.cookies.get("melereview_csrf")
    response = intruder.client.put(
        f"/api/users/{uid}/privacy",
        json={"progress_private": True},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 403
