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
