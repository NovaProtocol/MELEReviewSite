"""Reporting a question, and the administrator's queue."""

from __future__ import annotations


def _question(client, body: str = "A question worth checking") -> dict:
    token = client.cookies.get("melereview_csrf")
    response = client.post(
        "/api/questions",
        json={
            "topic_id": client.get("/api/subjects").json()[0]["topics"][0]["id"],
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


def _report(client, question_id: int, reason: str = "The answer key looks wrong"):
    token = client.cookies.get("melereview_csrf")
    return client.post(
        f"/api/questions/{question_id}/report",
        json={"reason": reason},
        headers={"X-CSRF-Token": token},
    )


def test_a_member_can_report_a_question(admin_client, member_factory):
    question = _question(admin_client)
    member = member_factory("reporter")
    assert _report(member.client, question["id"]).status_code == 201
    detail = member.client.get(f"/api/questions/{question['id']}").json()
    assert detail["reported_by_me"] is True


def test_reporting_twice_is_refused_while_the_first_is_open(admin_client):
    question = _question(admin_client)
    token = admin_client.cookies.get("melereview_csrf")
    first = admin_client.post(
        f"/api/questions/{question['id']}/report",
        json={"reason": "Wrong key"},
        headers={"X-CSRF-Token": token},
    )
    assert first.status_code == 201
    second = admin_client.post(
        f"/api/questions/{question['id']}/report",
        json={"reason": "Still wrong"},
        headers={"X-CSRF-Token": token},
    )
    assert second.status_code == 409


def test_an_empty_report_is_refused(admin_client):
    question = _question(admin_client)
    assert _report(admin_client, question["id"], "  ").status_code == 422


def test_reporting_does_not_hide_the_question(admin_client):
    question = _question(admin_client, "Still visible while reported")
    _report(admin_client, question["id"])
    detail = admin_client.get(f"/api/questions/{question['id']}").json()
    assert detail["is_hidden"] is False


def test_the_administrator_sees_the_queue(admin_client, member_factory):
    question = _question(admin_client, "Queued question")
    member = member_factory("queuereporter")
    _report(member.client, question["id"], "Choice B is also right")

    queue = admin_client.get("/api/admin/reports").json()["reports"]
    item = next(entry for entry in queue if entry["question_id"] == question["id"])
    assert item["reason"] == "Choice B is also right"
    assert item["reporter"] == member.username


def test_resolving_clears_it_from_the_queue(admin_client, member_factory):
    question = _question(admin_client, "Resolve me")
    member = member_factory("resolvereporter")
    _report(member.client, question["id"])
    item = next(
        entry
        for entry in admin_client.get("/api/admin/reports").json()["reports"]
        if entry["question_id"] == question["id"]
    )

    token = admin_client.cookies.get("melereview_csrf")
    settled = admin_client.post(
        f"/api/admin/reports/{item['id']}/resolve", headers={"X-CSRF-Token": token}
    )
    assert settled.status_code == 200
    assert settled.json()["status"] == "resolved"

    remaining = admin_client.get("/api/admin/reports").json()["reports"]
    assert all(entry["id"] != item["id"] for entry in remaining)


def test_a_member_cannot_read_the_queue(admin_client, member_factory):
    member = member_factory("queuepeeker")
    assert member.client.get("/api/admin/reports").status_code == 403


def test_the_overview_counts_open_reports(admin_client, member_factory):
    question = _question(admin_client, "Counted question")
    member = member_factory("countreporter")
    _report(member.client, question["id"])
    overview = admin_client.get("/api/admin/overview").json()
    assert overview["open_reports"] >= 1
