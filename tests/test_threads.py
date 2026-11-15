"""Replies: threads on solutions, votes, and who may take part."""

from __future__ import annotations


def _topic_id(client) -> int:
    return client.get("/api/subjects").json()[0]["topics"][0]["id"]


def _question(client, body: str = "Explain the expansion ratio") -> dict:
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


def _solve(client, question: dict) -> None:
    token = client.cookies.get("melereview_csrf")
    response = client.post(
        f"/api/questions/{question['id']}/attempt",
        json={"chosen": "A"},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200, response.text


def _solution(client, question: dict) -> dict:
    token = client.cookies.get("melereview_csrf")
    response = client.post(
        f"/api/questions/{question['id']}/solution",
        json={"body": "Here is my working."},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200, response.text
    return response.json()["solutions"][0]


def _reply(client, solution_id: int, body: str, parent_id: int | None = None):
    token = client.cookies.get("melereview_csrf")
    return client.post(
        f"/api/solutions/{solution_id}/replies",
        json={"body": body, "parent_id": parent_id},
        headers={"X-CSRF-Token": token},
    )


def _view(client, question: dict) -> dict:
    return client.get(f"/api/questions/{question['id']}").json()


def _find(replies: list[dict], reply_id: int) -> dict | None:
    for reply in replies:
        if reply["id"] == reply_id:
            return reply
        found = _find(reply["replies"], reply_id)
        if found:
            return found
    return None


def test_a_solution_carries_its_replies(admin_client):
    question = _question(admin_client)
    solution = _solution(admin_client, question)
    _solve(admin_client, question)

    assert (
        _reply(admin_client, solution["id"], "That step needs the steam tables.").status_code == 201
    )

    payload = _view(admin_client, question)
    thread = payload["solutions"][0]
    assert [reply["body"] for reply in thread["replies"]] == ["That step needs the steam tables."]


def test_a_reply_can_be_replied_to_and_so_on(admin_client):
    question = _question(admin_client)
    solution = _solution(admin_client, question)
    _solve(admin_client, question)

    first = _reply(admin_client, solution["id"], "Level one").json()
    second = _reply(admin_client, solution["id"], "Level two", first["id"]).json()
    third = _reply(admin_client, solution["id"], "Level three", second["id"]).json()
    assert third["parent_id"] == second["id"]

    thread = _view(admin_client, question)["solutions"][0]
    assert thread["replies"][0]["body"] == "Level one"
    assert thread["replies"][0]["replies"][0]["body"] == "Level two"
    assert thread["replies"][0]["replies"][0]["replies"][0]["body"] == "Level three"


def test_a_reply_cannot_be_attached_to_another_thread(admin_client):
    question = _question(admin_client)
    solution = _solution(admin_client, question)
    other = _solution(admin_client, _question(admin_client, "A second question"))
    _solve(admin_client, question)
    stray = _reply(admin_client, other["id"], "Elsewhere").json()

    response = _reply(admin_client, solution["id"], "Wrong thread", stray["id"])
    assert response.status_code == 404


def test_an_empty_reply_is_refused(admin_client):
    question = _question(admin_client)
    solution = _solution(admin_client, question)
    _solve(admin_client, question)
    assert _reply(admin_client, solution["id"], "   ").status_code == 422


def test_replying_needs_the_question_solved(admin_client, member_factory):
    question = _question(admin_client)
    solution = _solution(admin_client, question)

    stranger = member_factory("threadstranger")
    blocked = _reply(stranger.client, solution["id"], "Can I see this?")
    assert blocked.status_code == 403

    _solve(stranger.client, question)
    allowed = _reply(stranger.client, solution["id"], "Now I can")
    assert allowed.status_code == 201


def test_votes_on_a_solution_add_up(admin_client, member_factory):
    question = _question(admin_client)
    solution = _solution(admin_client, question)
    _solve(admin_client, question)
    voter = member_factory("threadvoter")
    _solve(voter.client, question)
    token = voter.client.cookies.get("melereview_csrf")

    url = f"/api/solutions/{solution['id']}/vote"
    up = voter.client.post(url, json={"direction": 1}, headers={"X-CSRF-Token": token})
    assert up.json() == {"score": 1, "my_vote": 1}

    # Direction is the vote to hold, so 0 takes it back. The page sends that when
    # the arrow already lit is clicked again.
    cleared = voter.client.post(url, json={"direction": 0}, headers={"X-CSRF-Token": token})
    assert cleared.json() == {"score": 0, "my_vote": 0}

    down = voter.client.post(url, json={"direction": -1}, headers={"X-CSRF-Token": token})
    assert down.json() == {"score": -1, "my_vote": -1}

    admin_token = admin_client.cookies.get("melereview_csrf")
    admin_up = admin_client.post(url, json={"direction": 1}, headers={"X-CSRF-Token": admin_token})
    assert admin_up.json()["score"] == 0

    thread = _view(admin_client, question)["solutions"][0]
    assert thread["score"] == 0
    assert thread["my_vote"] == 1


def test_votes_on_a_reply_add_up(admin_client):
    question = _question(admin_client)
    solution = _solution(admin_client, question)
    _solve(admin_client, question)
    reply = _reply(admin_client, solution["id"], "A reply worth a vote").json()
    token = admin_client.cookies.get("melereview_csrf")

    response = admin_client.post(
        f"/api/replies/{reply['id']}/vote",
        json={"direction": 1},
        headers={"X-CSRF-Token": token},
    )
    assert response.json() == {"score": 1, "my_vote": 1}

    thread = _view(admin_client, question)["solutions"][0]
    assert thread["replies"][0]["score"] == 1


def test_a_reply_can_be_deleted_by_its_author(admin_client):
    question = _question(admin_client)
    solution = _solution(admin_client, question)
    _solve(admin_client, question)
    reply = _reply(admin_client, solution["id"], "Delete me").json()
    token = admin_client.cookies.get("melereview_csrf")

    gone = admin_client.delete(f"/api/replies/{reply['id']}", headers={"X-CSRF-Token": token})
    assert gone.status_code == 204
    assert _view(admin_client, question)["solutions"][0]["replies"] == []


def test_a_reply_cannot_be_deleted_by_a_stranger(admin_client, member_factory):
    question = _question(admin_client)
    solution = _solution(admin_client, question)
    _solve(admin_client, question)
    reply = _reply(admin_client, solution["id"], "Not yours").json()

    stranger = member_factory("replystranger")
    _solve(stranger.client, question)
    token = stranger.client.cookies.get("melereview_csrf")
    denied = stranger.client.delete(f"/api/replies/{reply['id']}", headers={"X-CSRF-Token": token})
    assert denied.status_code == 403


def test_a_banned_authors_replies_leave_the_thread(admin_client, member_factory):
    question = _question(admin_client)
    solution = _solution(admin_client, question)
    member = member_factory("threadbanned")
    _solve(member.client, question)
    _reply(member.client, solution["id"], "Visible while I am here")
    assert len(_view(admin_client, question)["solutions"][0]["replies"]) == 1

    uid = member.client.get("/api/auth/me").json()["id"]
    token = admin_client.cookies.get("melereview_csrf")
    admin_client.post(f"/api/admin/users/{uid}/ban", headers={"X-CSRF-Token": token})

    assert _view(admin_client, question)["solutions"][0]["replies"] == []


def test_a_reply_under_a_removed_parent_is_lifted_not_lost(admin_client, member_factory):
    question = _question(admin_client)
    solution = _solution(admin_client, question)
    parent_author = member_factory("threadparent")
    child_author = member_factory("threadchild")
    _solve(parent_author.client, question)
    _solve(child_author.client, question)

    parent = _reply(parent_author.client, solution["id"], "The parent").json()
    _reply(child_author.client, solution["id"], "The child", parent["id"])

    internal = parent_author.client.get("/api/auth/me").json()["id"]
    token = admin_client.cookies.get("X-CSRF-Token") or admin_client.cookies.get("melereview_csrf")
    admin_client.post(f"/api/admin/users/{internal}/ban", headers={"X-CSRF-Token": token})

    thread = _view(admin_client, question)["solutions"][0]
    assert [reply["body"] for reply in thread["replies"]] == ["The child"]


def test_the_payload_carries_the_order_the_client_sorts_by(admin_client):
    """The page sorts in the browser, so both numbers have to be in the payload."""
    question = _question(admin_client)
    _solution(admin_client, question)
    _solve(admin_client, question)
    thread = _view(admin_client, question)["solutions"][0]
    assert "score" in thread
    assert thread["date_created"]


def test_a_solution_is_stored_as_its_prose(admin_client):
    question = _question(admin_client)
    solution = _solution(admin_client, question)
    assert solution["body"] == "Here is my working."
    assert solution["body_html"]


def test_a_downvoted_reply_is_still_shown(admin_client):
    """The score threshold hides questions. A reply is never hidden for its
    score: burying an unpopular answer is how a thread stops being a thread."""
    question = _question(admin_client)
    solution = _solution(admin_client, question)
    _solve(admin_client, question)
    reply = _reply(admin_client, solution["id"], "Unpopular but present").json()
    token = admin_client.cookies.get("melereview_csrf")

    for value in (-1,):
        admin_client.post(
            f"/api/replies/{reply['id']}/vote",
            json={"direction": value},
            headers={"X-CSRF-Token": token},
        )
    payload = _view(admin_client, question)
    assert payload["solutions"][0]["replies"][0]["score"] == -1
    assert payload["solutions"][0]["replies"][0]["body"] == "Unpopular but present"


def test_solutions_are_not_hidden_by_score_either(admin_client):
    question = _question(admin_client)
    solution = _solution(admin_client, question)
    _solve(admin_client, question)
    token = admin_client.cookies.get("melereview_csrf")
    admin_client.post(
        f"/api/solutions/{solution['id']}/vote",
        json={"direction": -1},
        headers={"X-CSRF-Token": token},
    )
    payload = _view(admin_client, question)
    assert len(payload["solutions"]) == 1


def test_a_reply_can_be_edited_by_its_author(admin_client):
    question = _question(admin_client)
    solution = _solution(admin_client, question)
    _solve(admin_client, question)
    reply = _reply(admin_client, solution["id"], "First wording").json()
    token = admin_client.cookies.get("melereview_csrf")

    edited = admin_client.put(
        f"/api/replies/{reply['id']}",
        json={"body": "Second wording"},
        headers={"X-CSRF-Token": token},
    )
    assert edited.status_code == 200
    assert edited.json()["body"] == "Second wording"
    thread = _view(admin_client, question)["solutions"][0]
    assert thread["replies"][0]["body"] == "Second wording"


def test_a_reply_cannot_be_edited_by_a_stranger(admin_client, member_factory):
    question = _question(admin_client)
    solution = _solution(admin_client, question)
    _solve(admin_client, question)
    reply = _reply(admin_client, solution["id"], "Mine").json()

    stranger = member_factory("replyeditor")
    _solve(stranger.client, question)
    token = stranger.client.cookies.get("melereview_csrf")
    denied = stranger.client.put(
        f"/api/replies/{reply['id']}",
        json={"body": "hijacked"},
        headers={"X-CSRF-Token": token},
    )
    assert denied.status_code == 403


def test_an_edited_reply_cannot_be_emptied(admin_client):
    question = _question(admin_client)
    solution = _solution(admin_client, question)
    _solve(admin_client, question)
    reply = _reply(admin_client, solution["id"], "Something").json()
    token = admin_client.cookies.get("melereview_csrf")
    response = admin_client.put(
        f"/api/replies/{reply['id']}", json={"body": "  "}, headers={"X-CSRF-Token": token}
    )
    assert response.status_code == 422
