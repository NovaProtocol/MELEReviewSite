from __future__ import annotations

from fastapi.testclient import TestClient

from wsgi import app


def _topic_id(admin_client) -> int:
    subjects = admin_client.get("/api/subjects").json()
    return subjects[0]["topics"][0]["id"]


def _question(
    admin_client, topic_id: int, body: str = "What is the entropy of the universe?"
) -> dict:
    token = admin_client.cookies.get("melereview_csrf")
    response = admin_client.post(
        "/api/questions",
        json={
            "topic_id": topic_id,
            "body": body,
            "choice_a": "Zero",
            "choice_b": "Increasing",
            "choice_c": "Constant",
            "choice_d": "Undefined",
            "correct_choice": "B",
            "kind": "identification",
        },
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_permission_bits_are_independent():
    from app import permissions

    combined = permissions.POST_QUESTION | permissions.INVITE
    assert permissions.has(combined, permissions.POST_QUESTION)
    assert permissions.has(combined, permissions.INVITE)
    assert not permissions.has(combined, permissions.MODERATE)
    assert permissions.ALL == 511, "nine bits now"
    assert permissions.EDIT_TOPIC_CONTENT == 256


def test_new_member_gets_the_default_grants(admin_client, member_factory):
    from app import permissions

    member = member_factory("defaults")
    me = member.client.get("/api/auth/me").json()
    assert me["permissions"] == permissions.DEFAULT
    assert "Post questions" in me["permission_labels"]


def test_member_without_post_question_cannot_create(admin_client, member_factory):
    from app import permissions

    member = member_factory("readonly")
    row = next(
        u
        for u in admin_client.get("/api/admin/users?per_page=200").json()["items"]
        if u["username"] == member.username
    )
    token = admin_client.cookies.get("melereview_csrf")
    stripped = row["permissions"] & ~permissions.POST_QUESTION
    updated = admin_client.put(
        f"/api/admin/users/{row['id']}/permissions",
        json={"permissions": stripped},
        headers={"X-CSRF-Token": token},
    )
    assert updated.status_code == 200

    topic_id = _topic_id(member.client)
    response = member.client.post(
        "/api/questions",
        json={
            "topic_id": topic_id,
            "body": "Should not be allowed",
            "choice_a": "a",
            "choice_b": "b",
            "choice_c": "c",
            "choice_d": "d",
            "correct_choice": "A",
            "kind": "identification",
        },
        headers={"X-CSRF-Token": member.client.cookies.get("melereview_csrf")},
    )
    assert response.status_code == 403
    assert member.client.get("/questions/new", follow_redirects=False).status_code == 403


def test_member_without_answer_permission_cannot_upload(admin_client, member_factory):
    from app import permissions

    member = member_factory("noanswer")
    row = next(
        u
        for u in admin_client.get("/api/admin/users?per_page=200").json()["items"]
        if u["username"] == member.username
    )
    token = admin_client.cookies.get("melereview_csrf")
    admin_client.put(
        f"/api/admin/users/{row['id']}/permissions",
        json={"permissions": row["permissions"] & ~permissions.ANSWER_QUESTION},
        headers={"X-CSRF-Token": token},
    )
    topic_id = _topic_id(member.client)
    question = _question(admin_client, topic_id)
    response = member.client.post(
        f"/api/questions/{question['id']}/solution",
        json={"body": "Let me try."},
        headers={"X-CSRF-Token": member.client.cookies.get("melereview_csrf")},
    )
    assert response.status_code == 403


def test_moderator_can_hide_and_admin_can_restore(admin_client, member_factory):
    from app import permissions

    moderator = member_factory("moderator")
    row = next(
        u
        for u in admin_client.get("/api/admin/users?per_page=200").json()["items"]
        if u["username"] == moderator.username
    )
    token = admin_client.cookies.get("melereview_csrf")
    admin_client.put(
        f"/api/admin/users/{row['id']}/permissions",
        json={"permissions": row["permissions"] | permissions.MODERATE},
        headers={"X-CSRF-Token": token},
    )

    topic_id = _topic_id(admin_client)
    question = _question(admin_client, topic_id, "A question that will be hidden")
    visible = member_factory("viewer")
    before = visible.client.get(f"/api/topics/{topic_id}/questions").json()
    assert any(q["id"] == question["id"] for q in before)

    hidden = moderator.client.post(
        f"/api/questions/{question['id']}/hide",
        headers={"X-CSRF-Token": moderator.client.cookies.get("melereview_csrf")},
    )
    assert hidden.status_code == 200
    assert hidden.json()["is_hidden"] is True

    after = visible.client.get(f"/api/topics/{topic_id}/questions").json()
    assert all(q["id"] != question["id"] for q in after)

    # The row is still there, and the administrator can see it.
    admin_view = admin_client.get(f"/api/topics/{topic_id}/questions").json()
    assert any(q["id"] == question["id"] for q in admin_view)

    content = admin_client.get("/api/admin/content").json()
    assert any(item["id"] == question["id"] for item in content["questions"])

    restored = admin_client.post(
        f"/api/admin/content/question/{question['id']}/restore",
        headers={"X-CSRF-Token": token},
    )
    assert restored.status_code == 200
    reappeared = visible.client.get(f"/api/topics/{topic_id}/questions").json()
    assert any(q["id"] == question["id"] for q in reappeared)


def test_banned_author_content_disappears_without_a_hide(admin_client, member_factory):
    token = admin_client.cookies.get("melereview_csrf")
    author = member_factory("bannedauthor")
    topic_id = _topic_id(author.client)
    question = _question(author.client, topic_id, "Written by someone who gets banned")

    reader = member_factory("reader")
    assert any(
        q["id"] == question["id"]
        for q in reader.client.get(f"/api/topics/{topic_id}/questions").json()
    )

    row = next(
        u
        for u in admin_client.get("/api/admin/users?per_page=200").json()["items"]
        if u["username"] == author.username
    )
    admin_client.post(f"/api/admin/users/{row['id']}/ban", headers={"X-CSRF-Token": token})

    remaining = reader.client.get(f"/api/topics/{topic_id}/questions").json()
    assert all(q["id"] != question["id"] for q in remaining)
    # Nothing was hidden and nothing was deleted: the ban is the only reason.
    content = admin_client.get("/api/admin/content").json()
    assert all(item["id"] != question["id"] for item in content["questions"])


def test_the_author_can_edit_their_own_question(admin_client, member_factory):
    member = member_factory("author")
    topic_id = _topic_id(member.client)
    question = _question(member.client, topic_id)
    edited = member.client.put(
        f"/api/questions/{question['id']}",
        json={
            "topic_id": topic_id,
            "body": "Edited question text",
            "choice_a": "a",
            "choice_b": "b",
            "choice_c": "c",
            "choice_d": "d",
            "correct_choice": "C",
            "kind": "identification",
        },
        headers={"X-CSRF-Token": member.client.cookies.get("melereview_csrf")},
    )
    assert edited.status_code == 200
    assert edited.json()["body"] == "Edited question text"
    assert edited.json()["correct_choice"] == "C"


def test_a_member_cannot_edit_someone_elses_question(admin_client, member_factory):
    owner = member_factory("owner")
    other = member_factory("intruder")
    topic_id = _topic_id(owner.client)
    question = _question(owner.client, topic_id)
    response = other.client.put(
        f"/api/questions/{question['id']}",
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
        headers={"X-CSRF-Token": other.client.cookies.get("melereview_csrf")},
    )
    assert response.status_code == 403


def test_a_wrong_answer_does_not_reveal_the_right_one(admin_client, member_factory):
    """A second try is only a try if the first wrong one gives nothing away."""
    member = member_factory("answerer")
    token = member.client.cookies.get("melereview_csrf")
    topic_id = _topic_id(member.client)
    question = _question(admin_client, topic_id, "Pick the right letter")
    url = f"/api/questions/{question['id']}/attempt"

    wrong = member.client.post(url, json={"chosen": "A"}, headers={"X-CSRF-Token": token})
    assert wrong.status_code == 200
    assert wrong.json()["is_correct"] is False
    assert wrong.json()["correct_choice"] is None, "the answer stays hidden while wrong"
    assert wrong.json()["solved"] is False
    assert wrong.json()["attempts"] == 1

    right = member.client.post(url, json={"chosen": "B"}, headers={"X-CSRF-Token": token})
    assert right.status_code == 200
    assert right.json()["is_correct"] is True
    assert right.json()["correct_choice"] == "B"
    assert right.json()["attempts"] == 2, "the second try counts"

    # A solved sheet is closed: further clicks are refused rather than counted.
    again = member.client.post(url, json={"chosen": "C"}, headers={"X-CSRF-Token": token})
    assert again.status_code == 409

    progress = member.client.get("/api/me/progress").json()
    assert progress["answered"] >= 1
    assert progress["solved"] >= 1
    assert progress["first_try_rate"] == 0.0, "their first answer was wrong"
    assert progress["overall_rate"] == 100.0


def test_a_first_try_correct_answer_scores_one_try(admin_client, member_factory):
    member = member_factory("firsttry")
    token = member.client.cookies.get("melereview_csrf")
    topic_id = _topic_id(member.client)
    question = _question(admin_client, topic_id, "Easy one")

    result = member.client.post(
        f"/api/questions/{question['id']}/attempt",
        json={"chosen": "B"},
        headers={"X-CSRF-Token": token},
    ).json()
    assert result["attempts"] == 1 and result["is_correct"] is True

    progress = member.client.get("/api/me/progress").json()
    assert progress["first_try_rate"] == 100.0
    assert progress["average_tries"] == 1.0


def test_favourite_and_personal_hide_are_independent(admin_client, member_factory):
    """Both flags can be on at once: saved for later, and out of the list."""
    member = member_factory("favouriteowner")
    token = member.client.cookies.get("melereview_csrf")
    topic_id = _topic_id(member.client)
    question = _question(admin_client, topic_id, "A question worth keeping")
    url = f"/api/questions/{question['id']}"

    favourite = member.client.post(f"{url}/favourite", headers={"X-CSRF-Token": token}).json()
    assert favourite["is_favourite"] is True
    assert favourite["is_hidden_by_me"] is False

    hidden = member.client.post(f"{url}/hide-for-me", headers={"X-CSRF-Token": token}).json()
    assert hidden["is_favourite"] is True, "starring then hiding must not clear the star"
    assert hidden["is_hidden_by_me"] is True

    listed = member.client.get(f"/api/topics/{topic_id}/questions").json()
    assert all(q["id"] != question["id"] for q in listed), "a hidden question leaves the list"

    with_hidden = member.client.get(f"/api/topics/{topic_id}/questions?show_hidden=true").json()
    assert any(q["id"] == question["id"] for q in with_hidden)

    only_favourites = member.client.get(f"/api/topics/{topic_id}/questions?favourites=true").json()
    assert [q["id"] for q in only_favourites] == [question["id"]]


def test_personal_hide_does_not_hide_from_anyone_else(admin_client, member_factory):
    one = member_factory("hider")
    other = member_factory("bystander")
    topic_id = _topic_id(one.client)
    question = _question(admin_client, topic_id, "Only I hid this")
    one.client.post(
        f"/api/questions/{question['id']}/hide-for-me",
        headers={"X-CSRF-Token": one.client.cookies.get("melereview_csrf")},
    )
    listing = other.client.get(f"/api/topics/{topic_id}/questions").json()
    assert any(q["id"] == question["id"] for q in listing)


def test_votes_add_up_and_clearing_works(admin_client, member_factory):
    voter = member_factory("voter")
    token = voter.client.cookies.get("melereview_csrf")
    topic_id = _topic_id(voter.client)
    question = _question(admin_client, topic_id, "Vote on this")
    url = f"/api/questions/{question['id']}/vote"

    up = voter.client.post(url, json={"direction": 1}, headers={"X-CSRF-Token": token}).json()
    assert up["score"] == 1 and up["vote"] == 1

    again = voter.client.post(url, json={"direction": 1}, headers={"X-CSRF-Token": token}).json()
    assert again["score"] == 0 and again["vote"] == 0, "the same vote twice clears it"

    down = voter.client.post(url, json={"direction": -1}, headers={"X-CSRF-Token": token}).json()
    assert down["score"] == -1 and down["vote"] == -1


def test_downvoted_questions_are_hidden_unless_asked_for(admin_client, member_factory):
    voter = member_factory("downvoter")
    reader = member_factory("reader2")
    token = voter.client.cookies.get("melereview_csrf")
    topic_id = _topic_id(voter.client)
    question = _question(admin_client, topic_id, "Probably a bad question")
    voter.client.post(
        f"/api/questions/{question['id']}/vote",
        json={"direction": -1},
        headers={"X-CSRF-Token": token},
    )

    default = reader.client.get(f"/api/topics/{topic_id}/questions").json()
    assert all(q["id"] != question["id"] for q in default), "spam stays out by default"

    shown = reader.client.get(f"/api/topics/{topic_id}/questions?show_downvoted=true").json()
    assert any(q["id"] == question["id"] for q in shown)


def test_solutions_unlock_only_after_a_correct_answer(admin_client, member_factory):
    """Opening a question is not enough, and being wrong is not enough either."""
    member = member_factory("nospoiler")
    token = member.client.cookies.get("melereview_csrf")
    topic_id = _topic_id(member.client)
    question = _question(admin_client, topic_id, "No spoilers here")
    member.client.post(
        f"/api/questions/{question['id']}/solution",
        json={"body": "My working."},
        headers={"X-CSRF-Token": token},
    )

    listing = member.client.get(f"/api/topics/{topic_id}/questions").json()
    card = next(q for q in listing if q["id"] == question["id"])
    assert card["solutions"] == []
    assert card["solution_count"] == 1, "the count labels the link"
    assert card["may_see_solutions"] is False

    detail = member.client.get(f"/api/questions/{question['id']}").json()
    assert detail["solutions"] == [], "unanswered means no working"
    assert detail["may_see_solutions"] is False

    member.client.post(
        f"/api/questions/{question['id']}/attempt",
        json={"chosen": "A"},
        headers={"X-CSRF-Token": token},
    )
    still = member.client.get(f"/api/questions/{question['id']}").json()
    assert still["solutions"] == [], "wrong means still no working"

    member.client.post(
        f"/api/questions/{question['id']}/attempt",
        json={"chosen": "B"},
        headers={"X-CSRF-Token": token},
    )
    unlocked = member.client.get(f"/api/questions/{question['id']}").json()
    assert len(unlocked["solutions"]) == 1
    assert unlocked["may_see_solutions"] is True


def test_topic_creation_requires_the_taxonomy_permission(admin_client, member_factory):
    from app import permissions

    member = member_factory("taxonomist")
    assert not permissions.has(
        member.client.get("/api/auth/me").json()["permissions"], permissions.MANAGE_TAXONOMY
    )
    response = member.client.post(
        "/api/admin/topics",
        json={"subject_id": 1, "name": "Should not exist"},
        headers={"X-CSRF-Token": member.client.cookies.get("melereview_csrf")},
    )
    assert response.status_code == 403


def test_admin_can_add_subjects_and_topics(admin_client):
    token = admin_client.cookies.get("melereview_csrf")
    subject = admin_client.post(
        "/api/admin/subjects",
        json={"name": "Engineering Economics"},
        headers={"X-CSRF-Token": token},
    )
    assert subject.status_code == 201
    topic = admin_client.post(
        "/api/admin/topics",
        json={"subject_id": subject.json()["id"], "name": "break even analysis"},
        headers={"X-CSRF-Token": token},
    )
    assert topic.status_code == 201

    subjects = admin_client.get("/api/subjects").json()
    created = next(s for s in subjects if s["name"] == "Engineering Economics")
    assert [t["name"] for t in created["topics"]] == ["break even analysis"]


def test_the_administrator_edits_another_members_identity(admin_client, member_factory):
    """Omnipotence means the administrator can change anyone's account, not just
    moderate their content."""
    member = member_factory("adminedit")
    uid = member.client.get("/api/auth/me").json()["uid"]
    token = admin_client.cookies.get("melereview_csrf")
    headers = {"X-CSRF-Token": token}

    renamed = admin_client.put(
        f"/api/users/{uid}/username",
        json={"username": "renamed_by_the_admin"},
        headers=headers,
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["username"] == "renamed_by_the_admin"
    assert member.client.get("/api/auth/me").json()["username"] == "renamed_by_the_admin"

    mailed = admin_client.put(
        f"/api/users/{uid}/email",
        json={"email": "reset-by-admin@example.com"},
        headers=headers,
    )
    assert mailed.status_code == 200
    assert mailed.json()["email"] == "reset-by-admin@example.com"

    bio = admin_client.put(
        f"/api/users/{uid}/bio", json={"bio": "Written by the administrator"}, headers=headers
    )
    assert bio.status_code == 200
    assert bio.json()["bio"] == "Written by the administrator"


def test_the_administrator_resets_a_password_without_knowing_it(admin_client, member_factory):
    member = member_factory("adminreset")
    uid = member.client.get("/api/auth/me").json()["uid"]
    token = admin_client.cookies.get("melereview_csrf")

    reset = admin_client.put(
        f"/api/users/{uid}/password",
        json={"new": "a-fresh-password"},
        headers={"X-CSRF-Token": token},
    )
    assert reset.status_code == 200, reset.text

    with TestClient(app) as fresh:
        fresh.get("/")
        token = fresh.cookies.get("melereview_csrf")
        signed_in = fresh.post(
            "/api/auth/login",
            json={"identifier": member.username, "password": "a-fresh-password"},
            headers={"X-CSRF-Token": token},
        )
    assert signed_in.status_code == 200, "the new password is the live one"


def test_a_member_still_proves_the_current_password_for_their_own(admin_client, member_factory):
    member = member_factory("ownpassword")
    uid = member.client.get("/api/auth/me").json()["uid"]
    token = member.client.cookies.get("melereview_csrf")

    wrong = member.client.put(
        f"/api/users/{uid}/password",
        json={"current": "not-the-password", "new": "another-password"},
        headers={"X-CSRF-Token": token},
    )
    assert wrong.status_code == 403

    right = member.client.put(
        f"/api/users/{uid}/password",
        json={"current": member.password, "new": "another-password"},
        headers={"X-CSRF-Token": token},
    )
    assert right.status_code == 200


def test_a_member_cannot_edit_another_members_account(admin_client, member_factory):
    owner = member_factory("accountowner")
    intruder = member_factory("accountintruder")
    uid = owner.client.get("/api/auth/me").json()["uid"]
    token = intruder.client.cookies.get("melereview_csrf")
    headers = {"X-CSRF-Token": token}

    for path, body in (
        ("username", {"username": "stolen_name"}),
        ("email", {"email": "stolen@example.com"}),
        ("bio", {"bio": "defaced"}),
        ("password", {"new": "stolen-password"}),
    ):
        response = intruder.client.put(f"/api/users/{uid}/{path}", json=body, headers=headers)
        assert response.status_code == 403, f"{path} was writable by a stranger"

    assert owner.client.get("/api/auth/me").json()["username"] == owner.username


def test_the_administrator_can_open_a_banned_members_profile(admin_client, member_factory):
    """A banned member is invisible to everyone except whoever has to fix them."""
    member = member_factory("bannedprofile")
    uid = member.client.get("/api/auth/me").json()["uid"]
    token = admin_client.cookies.get("melereview_csrf")

    internal_id = member.client.get("/api/auth/me").json()["id"]
    banned = admin_client.post(
        f"/api/admin/users/{internal_id}/ban", headers={"X-CSRF-Token": token}
    )
    assert banned.status_code in (200, 204), banned.text

    assert admin_client.get(f"/users/{uid}").status_code == 200
    assert admin_client.get(f"/users/{uid}/edit").status_code == 200
    # The banned member's own session is sent to the status page, not the profile.
    landed = member.client.get(f"/users/{uid}", follow_redirects=False)
    assert landed.status_code == 302
    assert landed.headers["location"] == "/status"


def test_the_account_page_carries_no_forms_on_a_read_only_profile(admin_client, member_factory):
    member = member_factory("readonlyprofile")
    uid = member.client.get("/api/auth/me").json()["uid"]
    page = admin_client.get(f"/users/{uid}").text
    for form in ("username-form", "email-form", "bio-form", "password-form", "avatar-input"):
        assert f'id="{form}"' not in page, f"{form} leaked into the profile page"
