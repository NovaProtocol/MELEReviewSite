"""Style guards carried over from the previous build, retargeted at app/."""

from __future__ import annotations

import re
from pathlib import Path


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


def test_every_page_uses_the_same_width_class():
    """A page that changes width on navigation reads as a different site.

    `/topics/1` was 1080px and `/topics/1/1` was 720px, so the working area shrank
    by 360px between two pages of the same section. One `.page` class, no modifiers.
    """
    css = Path("app/static/css/main.css").read_text()
    assert ".page--narrow" not in css
    assert ".page--wide" not in css

    for template in Path("app/templates").glob("*.html"):
        source = template.read_text()
        for match in re.findall(r'class="([^"]*)"', source):
            classes = match.split()
            if "page" in classes or "page--" in match:
                assert "page--narrow" not in classes, template.name
                assert "page--wide" not in classes, template.name
