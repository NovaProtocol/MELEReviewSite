"""Static regression tests for web/static/js/questions.js.

These tests catch two classes of regressions that previously caused silent failures
in the questions page:

1. The `renderQuestion` function must end with `list.appendChild(card)` so the
   rendered card actually becomes part of the DOM. Without it, the cards are
   built and discarded, the page shows "1 questions" but renders nothing.
   (regression: commit 08bdfe0 introduced this line to fix exactly that bug).

2. The file must not contain `/* ignore */` / `/* ignore malformed */` style
   silencing. Silent catch blocks hide bugs; the policy is to log and continue
   (or re-throw), never to swallow an error without a trace.
"""

from __future__ import annotations

from pathlib import Path

JS_PATH = Path(__file__).resolve().parent.parent / "web" / "static" / "js" / "questions.js"


def _load() -> str:
    return JS_PATH.read_text(encoding="utf-8")


def test_renders_question_card_appends_to_list():
    """renderQuestion must append the card to the list before returning."""
    src = _load()
    # The last meaningful statement of renderQuestion (before the closing brace)
    # must be `list.appendChild(card);`. We check for the literal pair.
    assert "list.appendChild(card)" in src, (
        "renderQuestion is missing `list.appendChild(card)`, questions will "
        "be built but never inserted into the DOM (count shows but no card)."
    )


def test_no_silenced_catch_blocks():
    """No `catch (e) { /* ignore */ }` or similar silent swallows."""
    src = _load()
    forbidden = [
        "/* ignore */",
        "/* ignore malformed */",
        "/* silent */",
        "/* swallow */",
        "/* noop */",
    ]
    for marker in forbidden:
        assert marker not in src, (
            f"questions.js contains silenced catch block: {marker!r}. "
            "Replace with console.error() so an unexpected error is visible."
        )


def test_has_top_level_load_log():
    """The first line of the file should log when the script is loaded.

    Without this, if the script fails to load (e.g. 404, syntax error), the
    browser shows nothing and the failure looks like a backend bug.
    """
    src = _load()
    first_nonempty = next((line for line in src.splitlines() if line.strip()), "")
    assert "console.log" in first_nonempty and "file loaded" in first_nonempty, (
        f"questions.js should start with a `console.log` that confirms the "
        f"script loaded; got: {first_nonempty!r}"
    )


def test_init_logs_dom_ready():
    """The DOMContentLoaded handler must log when it fires."""
    src = _load()
    # Find the DOMContentLoaded block
    assert "DOMContentLoaded" in src
    # And it should log right after entering
    assert "DOMContentLoaded fired" in src, (
        "DOMContentLoaded handler should log when it fires so the load path "
        "is observable in the browser console."
    )
