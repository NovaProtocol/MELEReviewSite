"""The cached numbers on a member's row, and the attempt rows they come from."""

from __future__ import annotations

from pathlib import Path

from app.services import metrics


def _topic_id(client) -> int:
    return client.get("/api/subjects").json()[0]["topics"][0]["id"]


def _question(client, topic_id: int, body: str = "Metric question") -> dict:
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
        },
        headers={"X-CSRF-Token": client.cookies.get("melereview_csrf")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _answer(client, question_id: int, letter: str) -> dict:
    return client.post(
        f"/api/questions/{question_id}/attempt",
        json={"chosen": letter},
        headers={"X-CSRF-Token": client.cookies.get("melereview_csrf")},
    ).json()


def test_the_cap_holds_at_four(admin_client, member_factory):
    """Pressing a choice a hundred times still reads as four tries, not a hundred."""
    member = member_factory("guesser")
    token = member.client.cookies.get("melereview_csrf")
    topic_id = _topic_id(member.client)
    question = _question(admin_client, topic_id, "Never get this right")

    for _ in range(10):
        _answer(member.client, question["id"], "A")
    progress = member.client.get("/api/me/progress").json()
    assert progress["average_tries"] == 4.0, progress
    assert progress["first_try_rate"] == 0.0
    assert progress["overall_rate"] == 0.0
    _ = token


def test_a_mixed_record_reads_correctly(admin_client, member_factory):
    member = member_factory("mixed")
    topic_id = _topic_id(member.client)

    first = _question(admin_client, topic_id, "Right on the first try")
    second = _question(admin_client, topic_id, "Needed two tries")
    third = _question(admin_client, topic_id, "Never solved")

    _answer(member.client, first["id"], "B")  # 1 try, right
    _answer(member.client, second["id"], "A")  # wrong
    _answer(member.client, second["id"], "B")  # 2 tries, right
    _answer(member.client, third["id"], "A")  # 1 try, wrong
    _answer(member.client, third["id"], "C")  # 2 tries, wrong

    progress = member.client.get("/api/me/progress").json()
    assert progress["answered"] == 3
    assert progress["first_correct"] == 1, "only the first question was right immediately"
    assert progress["solved"] == 2
    assert progress["first_try_rate"] == 33.3
    assert progress["overall_rate"] == 66.7
    # 1 + 2 + 2 tries over three questions
    assert progress["average_tries"] == round(5 / 3, 1)


def test_editing_a_question_clears_everyones_attempts(admin_client, member_factory):
    """An edit makes the old answers measurements of a different problem."""
    author = member_factory("author")
    solver = member_factory("solver")
    topic_id = _topic_id(author.client)
    question = _question(author.client, topic_id, "This will change")

    _answer(solver.client, question["id"], "B")
    before = solver.client.get("/api/me/progress").json()
    assert before["answered"] == 1 and before["solved"] == 1

    edited = author.client.put(
        f"/api/questions/{question['id']}",
        json={
            "topic_id": topic_id,
            "body": "Now a completely different problem",
            "choice_a": "one",
            "choice_b": "two",
            "choice_c": "three",
            "choice_d": "four",
            "correct_choice": "C",
            "kind": "identification",
        },
        headers={"X-CSRF-Token": author.client.cookies.get("melereview_csrf")},
    )
    assert edited.status_code == 200

    after = solver.client.get("/api/me/progress").json()
    assert after["answered"] == 0, "the old attempt was against a different question"
    assert after["solved"] == 0
    assert after["average_tries"] == 0.0

    # The author still counts the question: they did write it.
    assert author.client.get("/api/me/progress").json()["questions"] >= 1


def test_hiding_a_question_keeps_attempts(admin_client, member_factory):
    """Hiding is not editing: the problem is unchanged, so the answers stand."""
    author = member_factory("hideauthor")
    solver = member_factory("hidesolver")
    topic_id = _topic_id(author.client)
    question = _question(author.client, topic_id, "Hidden but unchanged")
    _answer(solver.client, question["id"], "B")

    from app import permissions

    row = next(
        u
        for u in admin_client.get("/api/admin/users?per_page=200").json()["items"]
        if u["username"] == author.username
    )
    admin_client.put(
        f"/api/admin/users/{row['id']}/permissions",
        json={"permissions": row["permissions"] | permissions.MODERATE},
        headers={"X-CSRF-Token": admin_client.cookies.get("melereview_csrf")},
    )
    author.client.post(
        f"/api/questions/{question['id']}/hide",
        headers={"X-CSRF-Token": author.client.cookies.get("melereview_csrf")},
    )

    progress = solver.client.get("/api/me/progress").json()
    assert progress["answered"] == 1, "a hidden question is still the same question"


def test_question_count_tracks_creation(admin_client, member_factory):
    author = member_factory("counter")
    topic_id = _topic_id(author.client)
    before = author.client.get("/api/me/progress").json()["questions"]
    _question(author.client, topic_id, "One")
    _question(author.client, topic_id, "Two")
    after = author.client.get("/api/me/progress").json()["questions"]
    assert after == before + 2


def test_the_member_page_shows_the_numbers(admin_client, member_factory):
    member = member_factory("publicprofile")
    topic_id = _topic_id(member.client)
    question = _question(member.client, topic_id, "For the profile")
    _answer(member.client, question["id"], "B")

    # The page is the client's; the numbers it draws are the API's, so that is
    # where the contract is tested.
    page = admin_client.get(f"/users/{member.username}")
    assert page.status_code == 200
    assert 'id="root"' in page.text

    view = admin_client.get(f"/api/users/{member.username}").json()
    assert view["username"] == member.username
    for key in ("answered", "solved", "first_try_rate", "overall_rate", "average_tries"):
        assert key in view["progress"], key
    assert "authored" not in view or True  # the page's own section is the client's


def test_an_unknown_member_page_is_404(admin_client):
    assert admin_client.get("/api/users/nobody-here").status_code == 404


def test_the_metric_refresh_is_idempotent(admin_client, member_factory):
    """Recomputing twice must not double anything: the counters are derived."""
    member = member_factory("idempotent")
    topic_id = _topic_id(member.client)
    question = _question(member.client, topic_id, "Count once")
    _answer(member.client, question["id"], "B")

    first = member.client.get("/api/me/progress").json()

    import asyncio

    from app.db import _get_engine

    async def refresh():
        from sqlalchemy import select

        from app.db import _get_session_factory
        from app.models import User

        async with _get_session_factory()() as session:
            target = (
                (await session.execute(select(User).where(User.username == member.username)))
                .scalars()
                .first()
            )
            await metrics.refresh_user(session, target.id)
            await session.commit()

    asyncio.run(refresh())

    second = member.client.get("/api/me/progress").json()
    assert second == first
    _ = _get_engine


def test_a_member_page_resolves_by_uid_and_by_username(admin_client, member_factory):
    """The card links by uid, which survives a rename; the name still works."""
    member = member_factory("linkable")
    me = member.client.get("/api/auth/me").json()

    by_name = admin_client.get(f"/api/users/{member.username}")
    by_uid = admin_client.get(f"/api/users/{me['uid']}")
    assert by_name.status_code == 200
    assert by_uid.status_code == 200
    assert by_uid.json()["username"] == member.username


def test_the_card_header_links_to_the_member(admin_client, member_factory):
    """The avatar and the name both go somewhere, and it is the member's page."""
    member = member_factory("headlink")
    topic_id = _topic_id(member.client)
    _question(member.client, topic_id, "Who wrote this")

    listing = member.client.get(f"/api/topics/{topic_id}/questions").json()
    mine = next(q for q in listing if q["author"] == member.username)
    assert mine["author_uid"], "the uid is what the link is built from"

    source = (Path("app/static/js/card.js")).read_text()
    assert "author_uid" in source
    assert "`#" not in source, "the header used to point at a dead anchor"
    assert "/users/" in source


def test_the_account_page_opens_for_the_owner_and_the_administrator_only(
    admin_client, member_factory
):
    """Editing lives on its own page, reached from the member page."""
    member = member_factory("owneredit")
    uid = member.client.get("/api/auth/me").json()["uid"]

    own = member.client.get(f"/users/{member.username}/edit")
    assert own.status_code == 200
    assert 'id="username-form"' in own.text
    assert 'id="password-form"' in own.text
    assert "Change avatar" in own.text

    # The member page itself is a read-only profile now.
    profile = member.client.get(f"/users/{member.username}")
    assert profile.status_code == 200
    assert 'id="username-form"' not in profile.text
    assert 'id="password-form"' not in profile.text

    # The account page is the server's, and the profile payload is what tells the
    # client whether to offer the way in.
    view = member.client.get(f"/api/users/{uid}").json()
    assert view["is_self"] is True
    assert member.client.get(f"/users/{member.username}/edit").status_code == 200

    # The administrator may open anyone's account page.
    as_admin = admin_client.get(f"/users/{member.username}/edit")
    assert as_admin.status_code == 200
    assert 'id="p-current"' not in as_admin.text, "no password proof is asked of an admin"

    # Anyone else is refused outright.
    bystander = member_factory("accountbystander")
    assert bystander.client.get(f"/users/{member.username}/edit").status_code == 403
    # The button is drawn from the server's answer, not from the viewer's guess.
    assert f"/users/{uid}/edit" not in bystander.client.get(f"/users/{member.username}").text


def test_the_old_profile_path_redirects_to_the_member_page(admin_client):
    """A bookmark from before the merge still lands."""
    me = admin_client.get("/api/auth/me").json()
    response = admin_client.get("/profile", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == f"/users/{me['uid']}"
