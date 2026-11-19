"""The workspace shell and the formula index."""

from __future__ import annotations


def test_the_workspace_renders_for_a_signed_in_member(admin_client):
    response = admin_client.get("/app")
    assert response.status_code == 200
    html = response.text
    assert 'id="root"' in html
    assert "window.__MELE__" in html
    assert "specialists" in html


def test_a_guest_is_sent_to_the_front_door(client):
    response = client.get("/app", follow_redirects=False)
    assert response.status_code in (302, 303, 307)


def test_the_formula_search_reads_the_pages(admin_client):
    html = admin_client.get("/api/formulas?q=stress").json()
    assert "results" in html
    for row in html["results"]:
        assert row["topic_id"] > 0
        assert row["tex"]


def test_a_search_with_no_terms_is_empty(admin_client):
    assert admin_client.get("/api/formulas?q=").json()["results"] == []


def test_the_layout_travels_with_the_member(admin_client):
    """The account holds the arrangement, so a second machine inherits it."""
    token = admin_client.cookies.get("melereview_csrf")
    empty = admin_client.get("/api/workspace/layout").json()
    assert empty["layout"] in (None, "")

    saved = admin_client.put(
        "/api/workspace/layout",
        json={"layout": '{"grid":1}', "saved_at": 1_000},
        headers={"X-CSRF-Token": token},
    )
    assert saved.status_code == 200
    assert admin_client.get("/api/workspace/layout").json()["layout"] == '{"grid":1}'


def test_an_older_layout_never_overwrites_a_newer_one(admin_client):
    """Two browsers, one account: the newer edit wins and the older is refused."""
    token = admin_client.cookies.get("melereview_csrf")
    admin_client.put(
        "/api/workspace/layout",
        json={"layout": '{"newer":true}', "saved_at": 5_000},
        headers={"X-CSRF-Token": token},
    )

    stale = admin_client.put(
        "/api/workspace/layout",
        json={"layout": '{"older":true}', "saved_at": 4_000},
        headers={"X-CSRF-Token": token},
    )
    assert stale.status_code == 200
    # Refused, and handed the winner back so the client can adopt it.
    assert stale.json()["layout"] == '{"newer":true}'
    assert stale.json()["rejected"] is True


def test_a_solution_cannot_be_published_before_the_answer_is_right(admin_client, member_factory):
    """A disabled switch is a courtesy; the rule lives here.

    Publishing is a claim that the working answers the question, so it is earned the
    same way reading other people's solutions is.
    """
    member = member_factory("publisher")
    token = member.client.cookies.get("melereview_csrf")
    topic = admin_client.get("/api/subjects").json()[0]["topics"][0]["id"]
    created = admin_client.post(
        "/api/questions",
        json={
            "topic_id": topic,
            "body": "Gate check",
            "choice_a": "a",
            "choice_b": "b",
            "choice_c": "c",
            "choice_d": "d",
            "correct_choice": "A",
            "kind": "identification",
        },
        headers={"X-CSRF-Token": admin_client.cookies.get("melereview_csrf")},
    )
    question_id = created.json()["id"]

    refused = member.client.put(
        f"/api/questions/{question_id}/draft",
        json={"body": "My working", "publish": True},
        headers={"X-CSRF-Token": token},
    )
    assert refused.status_code == 403
    assert "Answer the question correctly" in refused.json()["error"]["message"]

    # The working itself is still saved: writing is always allowed.
    draft = member.client.get(f"/api/questions/{question_id}/draft").json()
    assert draft["body"] == "My working"

    member.client.post(
        f"/api/questions/{question_id}/attempt",
        json={"chosen": "A"},
        headers={"X-CSRF-Token": token},
    )
    allowed = member.client.put(
        f"/api/questions/{question_id}/draft",
        json={"body": "My working", "publish": True},
        headers={"X-CSRF-Token": token},
    )
    assert allowed.status_code == 200
    assert allowed.json()["my_solution"] is not None


def test_a_formula_answers_its_unknown(admin_client):
    """Enter what you know, get the rest: the whole point of the solver."""
    solved = admin_client.post(
        "/api/formulas/solve",
        json={"equation": "y = m*x + b", "known": {"m": 1, "b": 3, "y": 7}, "unknown": "x"},
        headers={"X-CSRF-Token": admin_client.cookies.get("melereview_csrf")},
    )
    assert solved.status_code == 200
    assert solved.json()["value"] == 4


def test_a_formula_answers_a_different_unknown(admin_client):
    """y is on the left, but it can also be what you are looking for."""
    solved = admin_client.post(
        "/api/formulas/solve",
        json={"equation": "y = m*x + b", "known": {"m": 2, "x": 5, "b": 1}, "unknown": "y"},
        headers={"X-CSRF-Token": admin_client.cookies.get("melereview_csrf")},
    )
    assert solved.status_code == 200
    assert solved.json()["value"] == 11


def test_the_catalogue_is_listed(admin_client):
    listed = admin_client.get("/api/formulas/list?q=reynolds").json()["results"]
    assert listed
    assert listed[0]["variables"]
    assert listed[0]["equation"]


def test_the_solver_says_when_there_is_no_answer(admin_client):
    """A formula with no root in range is a wrong entry, not a number."""
    response = admin_client.post(
        "/api/formulas/solve",
        json={"equation": "x^2 = -1", "known": {}, "unknown": "x"},
        headers={"X-CSRF-Token": admin_client.cookies.get("melereview_csrf")},
    )
    assert response.status_code == 422
