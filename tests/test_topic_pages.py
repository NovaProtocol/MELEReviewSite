"""Topic pages: the moved addresses, and the Resources / Reference panels."""

from __future__ import annotations

from app import permissions


def _topic(client) -> int:
    return client.get("/api/subjects").json()[0]["topics"][0]["id"]


def _save(client, topic_id: int, kind: str, body: str):
    token = client.cookies.get("melereview_csrf")
    return client.put(
        f"/api/topics/{topic_id}/pages/{kind}",
        json={"body": body},
        headers={"X-CSRF-Token": token},
    )


def test_a_topic_lives_under_library_now(admin_client):
    topic = _topic(admin_client)
    page = admin_client.get(f"/library/{topic}")
    assert page.status_code == 200
    for tab in ("resources", "problems", "reference"):
        assert f'data-tab="{tab}"' in page.text
        assert f'data-panel="{tab}"' in page.text


def test_the_old_address_redirects(admin_client):
    topic = _topic(admin_client)
    response = admin_client.get(f"/topics/{topic}", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == f"/library/{topic}"

    question = admin_client.get(f"/topics/{topic}/1", follow_redirects=False)
    assert question.status_code == 301
    assert question.headers["location"] == f"/library/{topic}/1"


def test_an_empty_panel_still_renders(admin_client):
    topic = _topic(admin_client)
    page = admin_client.get(f"/library/{topic}")
    assert "Nothing here yet." in page.text


def test_the_administrator_permission_is_a_new_bit():
    assert permissions.EDIT_TOPIC_CONTENT == 1 << 8
    assert permissions.EDIT_TOPIC_CONTENT & permissions.ALL
    assert permissions.EDIT_TOPIC_CONTENT & permissions.DEFAULT == 0


def test_the_system_administrator_can_write_a_panel(admin_client):
    topic = _topic(admin_client)
    saved = _save(admin_client, topic, "resources", "## Notes\n\nThe mean is $\\bar{x}$.")
    assert saved.status_code == 200

    page = admin_client.get(f"/library/{topic}").text
    assert "<h2>Notes</h2>" in page
    assert 'class="math-inline"' in page


def test_a_member_without_the_bit_cannot_edit(admin_client, member_factory):
    topic = _topic(admin_client)
    member = member_factory("plainmember")

    page = member.client.get(f"/library/{topic}/pages/resources/edit")
    assert page.status_code == 403
    assert _save(member.client, topic, "resources", "nope").status_code == 403


def test_a_member_with_the_bit_can_edit(admin_client, member_factory):
    topic = _topic(admin_client)
    member = member_factory("pageadmin")
    row = next(
        user
        for user in admin_client.get("/api/admin/users?per_page=200").json()["items"]
        if user["username"] == member.username
    )
    token = admin_client.cookies.get("melereview_csrf")
    admin_client.put(
        f"/api/admin/users/{row['id']}/permissions",
        json={"permissions": row["permissions"] | permissions.EDIT_TOPIC_CONTENT},
        headers={"X-CSRF-Token": token},
    )

    edit = member.client.get(f"/library/{topic}/pages/reference/edit")
    assert edit.status_code == 200
    assert 'id="f-page"' in edit.text
    assert _save(member.client, topic, "reference", "Cheat sheet.").status_code == 200


def test_an_unknown_panel_is_refused(admin_client):
    topic = _topic(admin_client)
    assert admin_client.get(f"/library/{topic}/pages/syllabus/edit").status_code == 404
    assert _save(admin_client, topic, "syllabus", "x").status_code == 404


def test_the_page_keeps_its_source_for_the_editor(admin_client):
    topic = _topic(admin_client)
    _save(admin_client, topic, "resources", "**bold** source here")
    edit = admin_client.get(f"/library/{topic}/pages/resources/edit").text
    assert "**bold** source here" in edit
