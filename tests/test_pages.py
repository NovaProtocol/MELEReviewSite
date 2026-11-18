from __future__ import annotations

from conftest import register_with_invite


def test_the_front_door_is_the_client_for_a_guest(client):
    """A guest gets the landing shell; the form and the copy are the client's."""
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="root"' in response.text


def test_a_member_never_sees_the_sign_in_page(admin_client):
    response = admin_client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/problem-sets"


def test_register_page_asks_for_an_invitation_code(client):
    response = client.get("/register")
    assert response.status_code == 200
    assert 'id="register-code"' in response.text
    assert 'id="register-form"' in response.text


def test_register_page_accepts_a_prefilled_code(client):
    response = client.get("/register?code=abcdef0123456789")
    assert 'value="abcdef0123456789"' in response.text


def test_signed_in_user_goes_straight_to_the_library(admin_client):
    landing = admin_client.get("/", follow_redirects=False)
    assert landing.status_code == 302
    assert landing.headers["location"] == "/problem-sets"

    # /library is a bookmark from the old shape; the problem sets are the address.
    moved = admin_client.get("/library", follow_redirects=False)
    assert moved.status_code == 302
    assert moved.headers["location"] == "/problem-sets"

    library = admin_client.get("/problem-sets")
    assert library.status_code == 200
    assert 'id="root"' in library.text
    subjects = admin_client.get("/api/subjects").json()
    names = {subject["name"] for subject in subjects}
    assert {"Mathematics", "Power & Industrial Plant Engineering"} <= names


def test_library_lists_the_seeded_subjects(admin_client):
    all_subjects = admin_client.get("/api/subjects").json()
    subjects = [s for s in all_subjects if s["name"] != "Engineering Economics"]
    assert sum(len(s["topics"]) for s in subjects) == 58
    assert len(subjects) == 3
    assert len(subjects[0]["topics"]) == 12
    assert len(subjects[1]["topics"]) == 24
    assert len(subjects[2]["topics"]) == 22


def test_topic_page_renders(admin_client):
    topic_id = admin_client.get("/api/subjects").json()[0]["topics"][0]["id"]
    response = admin_client.get(f"/resource/{topic_id}")
    assert response.status_code == 200
    assert 'id="root"' in response.text
    # What the page needs is the data, and that is the API's job, not the shell's.
    questions = admin_client.get(f"/api/topics/{topic_id}/questions").json()
    assert isinstance(questions, list)


def test_question_form_renders_for_an_author(admin_client):
    response = admin_client.get("/questions/new")
    assert response.status_code == 200
    assert 'id="question-form"' in response.text


def test_the_account_page_shows_the_invitations(admin_client):
    me = admin_client.get("/api/auth/me").json()
    response = admin_client.get(f"/users/{me['uid']}/edit")
    assert response.status_code == 200
    assert me["uid"] in response.text
    assert 'id="invite-list"' in response.text


def test_admin_page_is_the_client(admin_client):
    response = admin_client.get("/admin")
    assert response.status_code == 200
    assert 'id="root"' in response.text
    # The tabs are the client's; what has to hold is that the API behind each one
    # answers for an administrator.
    assert admin_client.get("/api/admin/users").status_code == 200
    assert admin_client.get("/api/admin/overview").status_code == 200


def test_tool_pages_render_without_the_app_chrome(admin_client):
    for slug in ("unit", "thermo", "fluids", "heat", "strength", "psychro", "machine"):
        response = admin_client.get(f"/tools/{slug}")
        assert response.status_code == 200, slug
        assert "tool-body" in response.text
        assert "ui-navbar" not in response.text


def test_unknown_tool_is_a_404(admin_client):
    assert admin_client.get("/tools/nonsense").status_code == 404


def test_error_page_is_styled(admin_client):
    response = admin_client.get("/no-such-page")
    assert response.status_code == 404
    assert "404" in response.text
    assert "auth-card" in response.text


def test_health_endpoint(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_request_id_header_on_every_response(client):
    assert client.get("/health").headers.get("x-request-id")


def test_html_pages_are_never_publicly_cacheable(admin_client):
    """Under the test deployment (debug) nothing is storable at all."""
    for path in ("/", "/library", "/profile", "/admin"):
        response = admin_client.get(path, follow_redirects=False)
        assert response.headers.get("cache-control") == "no-store", path


def test_static_assets_are_served(admin_client):
    response = admin_client.get("/static/css/main.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]


def test_a_status_page_stays_reachable_while_banned(admin_client, member_factory):
    token = admin_client.cookies.get("melereview_csrf")
    member = member_factory("notice")
    row = next(
        u
        for u in admin_client.get("/api/admin/users?per_page=200").json()["items"]
        if u["username"] == member.username
    )
    admin_client.post(f"/api/admin/users/{row['id']}/ban", headers={"X-CSRF-Token": token})
    notice = member.client.get("/status")
    assert notice.status_code == 200
    # Other pages bounce back to the notice rather than showing app content.
    for path in ("/problem-sets", "/app", "/resource/1"):
        response = member.client.get(path, follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/status"


def test_revoked_user_is_sent_to_the_notice_not_the_login(admin_client, member_factory):
    root = member_factory("noticechain")
    code = root.invite_code()
    from conftest import app
    from fastapi.testclient import TestClient

    with TestClient(app) as child:
        child.get("/")
        register_with_invite(child, code, "noticechild")
        token = admin_client.cookies.get("melereview_csrf")
        row = next(
            u
            for u in admin_client.get("/api/admin/users?per_page=200").json()["items"]
            if u["username"] == root.username
        )
        admin_client.post(
            f"/api/admin/users/{row['id']}/revoke-subtree", headers={"X-CSRF-Token": token}
        )
        landing = child.get("/", follow_redirects=False)
        assert landing.status_code == 302
        # A revoked account is told why, wherever it lands.
        assert landing.headers["location"] in ("/status", "/problem-sets")
        assert child.get("/problem-sets", follow_redirects=False).status_code == 302


def test_the_question_page_renders_and_gates_the_solutions(admin_client):
    """The page must not carry solution markup until the visitor asks for it."""
    topic_id = admin_client.get("/api/subjects").json()[0]["topics"][0]["id"]
    created = admin_client.post(
        "/api/questions",
        json={
            "topic_id": topic_id,
            "body": "Page render check",
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

    page = admin_client.get(f"/problem-sets/{topic_id}/{question_id}")
    assert page.status_code == 200
    assert 'id="root"' in page.text

    # The gate is the API's now, and it is the thing worth testing: the payload
    # must not carry other people's solutions before a correct answer.
    view = admin_client.get(f"/api/questions/{question_id}").json()
    assert "solutions" in view
    assert view["may_see_solutions"] is True, "a moderator keeps their view"


def test_the_question_page_rejects_a_mismatched_topic(admin_client):
    topic_id = admin_client.get("/api/subjects").json()[0]["topics"][0]["id"]
    created = admin_client.post(
        "/api/questions",
        json={
            "topic_id": topic_id,
            "body": "Wrong topic",
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
    # The page is the client's and always renders; the API is what refuses a
    # question under the wrong topic, which is where the check belongs.
    assert (
        admin_client.get(f"/api/questions/{question_id}?topic_id={topic_id + 999}").status_code
        == 404
    )


def test_the_question_page_needs_a_session(client):
    # The old address redirects first, and the new one refuses without a session.
    moved = client.get("/library/1/1", follow_redirects=False)
    assert moved.status_code == 302
    assert client.get("/problem-sets/1/1", follow_redirects=False).status_code == 302


def test_a_topic_can_be_read_through_the_api(admin_client):
    """The write side existed without a read side, so only the Jinja page could
    show the notes. A client other than that page needs both."""
    response = admin_client.get("/api/topics/1/pages")
    assert response.status_code == 200
    pages = response.json()
    assert set(pages) == {"resources", "reference"}
    for page in pages.values():
        assert "html" in page
        assert "may_edit" in page
        assert "body" not in page, "the source is not needed to render it"
