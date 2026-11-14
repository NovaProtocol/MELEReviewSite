from __future__ import annotations


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
    assert permissions.ALL == 255


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
        if u["username"] == "readonly"
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
        if u["username"] == "noanswer"
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
        files={"file": ("x.png", b"\x89PNG\r\n\x1a\nrest", "image/png")},
        headers={"X-CSRF-Token": member.client.cookies.get("melereview_csrf")},
    )
    assert response.status_code == 403


def test_moderator_can_hide_and_admin_can_restore(admin_client, member_factory):
    from app import permissions

    moderator = member_factory("moderator")
    row = next(
        u
        for u in admin_client.get("/api/admin/users?per_page=200").json()["items"]
        if u["username"] == "moderator"
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
        if u["username"] == "bannedauthor"
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
        },
        headers={"X-CSRF-Token": other.client.cookies.get("melereview_csrf")},
    )
    assert response.status_code == 403


def test_attempt_is_recorded_and_reveals_the_answer(admin_client, member_factory):
    member = member_factory("answerer")
    topic_id = _topic_id(member.client)
    question = _question(admin_client, topic_id, "Pick the right letter")

    wrong = member.client.post(
        f"/api/questions/{question['id']}/attempt",
        json={"chosen": "A"},
        headers={"X-CSRF-Token": member.client.cookies.get("melereview_csrf")},
    )
    assert wrong.status_code == 200
    assert wrong.json()["is_correct"] is False
    assert wrong.json()["correct_choice"] == "B"

    progress = member.client.get("/api/me/progress").json()
    assert progress["answered"] >= 1


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


def test_the_question_page_lists_no_solutions_until_asked(admin_client, member_factory):
    """The list endpoint carries no solutions at all, so a card cannot spoil one."""
    member = member_factory("nospoiler")
    topic_id = _topic_id(member.client)
    question = _question(admin_client, topic_id, "No spoilers here")
    member.client.post(
        f"/api/questions/{question['id']}/solution",
        files={"file": ("s.png", b"\x89PNG\r\n\x1a\nrest", "image/png")},
        headers={"X-CSRF-Token": member.client.cookies.get("melereview_csrf")},
    )

    listing = member.client.get(f"/api/topics/{topic_id}/questions").json()
    card = next(q for q in listing if q["id"] == question["id"])
    assert card["solutions"] == []
    assert card["solution_count"] == 1, "the count is there so the link can be labelled"

    detail = member.client.get(f"/api/questions/{question['id']}").json()
    assert len(detail["solutions"]) == 1


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
