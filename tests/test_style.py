"""Style guards carried over from the previous build, retargeted at app/."""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def _python_files():
    return sorted(Path("app").rglob("*.py"))


def test_no_print_in_app():
    for path in _python_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            assert "print(" not in line, f"{path}:{number} uses print()"


def test_no_trailing_inline_comments():
    """Comments go above the line, with a tool directive as the only exception."""
    allowed = ("# type: ignore", "# noqa", "# pragma:", "# fmt:", "# nosec")
    for path in _python_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or any(a in line for a in allowed):
                continue
            if re.search(r"\S\s+#\s", line):
                pytest.fail(f"{path}:{number} has a trailing comment: {stripped!r}")


def test_no_bare_todo():
    for path in _python_files():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "TODO" in line and "TODO(" not in line:
                pytest.fail(f"{path} has a bare TODO: {line.strip()!r}")


def test_javascript_has_no_stray_console_log():
    allowed = ("file loaded", "DOMContentLoaded fired")
    for path in Path("app/static/js").rglob("*.js"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "console.log" in line and not any(a in line for a in allowed):
                pytest.fail(f"{path}:{number} has console.log: {line.strip()!r}")


def test_templates_do_not_reference_the_retired_block_editor():
    for path in Path("app/templates").rglob("*.html"):
        source = path.read_text(encoding="utf-8")
        assert "solution_blocks" not in source, path
        assert "MathQuill" not in source, path
        assert "blocks-editor" not in source, path


def test_page_scripts_do_not_share_top_level_bindings():
    """Two page scripts load on the same page, so each needs its own scope.

    `base.html` loads app.js plus the page's script; a top-level `const` in two of
    them is a redeclaration error that kills both, which is how the sign-in form
    silently stopped submitting.
    """
    page_scripts = [
        "auth.js",
        "profile.js",
        "topic.js",
        "question_form.js",
        "admin.js",
    ]
    for name in page_scripts:
        source = (Path("app/static/js") / name).read_text(encoding="utf-8")
        body = "\n".join(
            line
            for line in source.splitlines()
            if line.strip() and not line.strip().startswith("//")
        )
        assert "(function () {" in body, f"{name} is not wrapped in an IIFE"
        assert body.rstrip().endswith("})();"), f"{name} does not close its IIFE"


def test_no_dead_endpoints_left_in_javascript():
    for path in Path("app/static/js").rglob("*.js"):
        source = path.read_text(encoding="utf-8")
        assert '"/api/cycle"' not in source, path
        assert "/api/auth/accounts" not in source, path
        assert "/api/questions/undefined" not in source, path


def test_pyproject_keeps_ruff_and_mypy():
    import tomllib

    data = tomllib.loads(Path("pyproject.toml").read_text())
    assert "ruff" in data["tool"]
    assert "mypy" in data["tool"]
    assert data["project"]["requires-python"] == ">=3.14"


def test_the_content_column_is_centred_not_pinned_left():
    """A `max-width` with no auto margins leaves the page flush left on a wide screen.

    That is what `/library` looked like: 1180px of content with 740px of dead space
    to its right, because a later rule zeroed the right margin.
    """
    css = Path("app/static/css/main.css").read_text()
    rule = next(
        line
        for line in css.splitlines()
        if line.startswith(".app-shell:not(.app-shell--anon) .app-main")
    )
    assert "max-width" in rule
    assert "margin-inline: auto" in rule

    assert "margin-right: 0" not in css, "a zeroed right margin defeats the centring"
