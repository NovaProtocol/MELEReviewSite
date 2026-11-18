"""Every form that carries a secret must fail safely.

A `<form>` with no `method` submits a GET, so any script that has not loaded turns
the field values into a query string: a password in the address bar, in history, in
the referrer, in the server's access log. That is a real leak, and it is invisible
until it happens. Every form therefore names its method explicitly.
"""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "app" / "templates"
FORM = re.compile(r"<form\b[^>]*>", re.I)


def forms() -> list[str]:
    found: list[str] = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        found.extend(FORM.findall(path.read_text()))
    return found


def test_every_form_names_a_method():
    naked = [tag for tag in forms() if "method=" not in tag.lower()]
    assert naked == [], (
        "a form without a method submits a GET and puts its fields in the URL: " + "; ".join(naked)
    )


def test_a_secret_form_is_never_a_get():
    with_password = [
        tag for tag in forms() if 'method="post"' in tag.lower() or "method='post'" in tag.lower()
    ]
    assert with_password
    for tag in forms():
        assert not ("password" in tag.lower() and 'method="get"' in tag.lower())


def test_the_login_form_cannot_fall_back_to_the_address_bar():
    """The login form is the client's now, and it does not submit a form at all.

    It posts JSON from script, so there is no native submit to serialise a password
    into the query string; every Jinja form is checked above for the old failure.
    """
    source = (
        Path(__file__).resolve().parent.parent / "frontend" / "src" / "pages" / "SignInPage.tsx"
    ).read_text()
    assert "onSubmit={submit}" in source
    assert 'method: "POST"' in source
    assert "identifier" in source and "password" in source


def test_a_native_login_post_does_not_write_a_session(client):
    """Without the JSON body it is refused, rather than half-accepted."""
    response = client.post(
        "/api/auth/login",
        data={"identifier": "admin", "password": "password"},
        follow_redirects=False,
    )
    assert response.status_code in (403, 422)
    assert not response.cookies.get("melereview_session")
