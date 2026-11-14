from __future__ import annotations

from conftest import register_with_invite


def test_landing_is_a_landing_page_and_a_login_form(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.text
    assert 'id="login-form"' in body
    assert 'id="login-identifier"' in body
    assert 'id="login-password"' in body
    assert 'id="register-link"' in body
    assert 'id="demo-button"' in body
    assert "disabled" in body.split('id="demo-button"')[1].split(">")[0]
    assert "Mathematics" in body


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
    assert landing.headers["location"] == "/library"

    library = admin_client.get("/library")
    assert library.status_code == 200
    assert "Subjects" in library.text
    assert "Mathematics" in library.text
    assert "Power &amp; Industrial Plant Engineering" in library.text
    assert "Machine Design &amp; Shop Practice" in library.text


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
    response = admin_client.get(f"/topics/{topic_id}")
    assert response.status_code == 200
    assert 'id="q-list"' in response.text
    assert f'data-topic="{topic_id}"' in response.text


def test_question_form_renders_for_an_author(admin_client):
    response = admin_client.get("/questions/new")
    assert response.status_code == 200
    assert 'id="question-form"' in response.text


def test_profile_page_shows_the_uid(admin_client):
    me = admin_client.get("/api/auth/me").json()
    response = admin_client.get("/profile")
    assert response.status_code == 200
    assert me["uid"] in response.text
    assert 'id="invite-list"' in response.text


def test_admin_page_lists_the_tabs(admin_client):
    response = admin_client.get("/admin")
    assert response.status_code == 200
    for tab in (
        'data-tab="users"',
        'data-tab="invites"',
        'data-tab="content"',
        'data-tab="taxonomy"',
    ):
        assert tab in response.text
    assert 'id="confirm-modal"' in response.text


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
        if u["username"] == "notice"
    )
    admin_client.post(f"/api/admin/users/{row['id']}/ban", headers={"X-CSRF-Token": token})
    notice = member.client.get("/status")
    assert notice.status_code == 200
    # Other pages bounce back to the notice rather than showing app content.
    for path in ("/library", "/profile"):
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
            if u["username"] == "noticechain"
        )
        admin_client.post(
            f"/api/admin/users/{row['id']}/revoke-subtree", headers={"X-CSRF-Token": token}
        )
        landing = child.get("/", follow_redirects=False)
        assert landing.status_code == 302
        assert landing.headers["location"] == "/status"
