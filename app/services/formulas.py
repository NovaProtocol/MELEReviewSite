"""A searchable index of the formulas the book contains.

The formulas live inside the topic pages as TeX, written by whoever wrote the
notes. This reads them back out, keeps a little of the sentence around each one,
and answers a text search over that. The index is rebuilt when a page changes, so
there is no separate store to go stale.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Topic, TopicPage

# A formula is one expression: a display block, or a single-line inline span. A
# block that wraps several lines is a worked example, not a formula to look up.
BLOCK = re.compile(r"```.*?```", re.S)
# Bounded on both sides and never across a blank line: an unbalanced $$ in a
# scanned chapter would otherwise swallow a whole page and keep going.
DISPLAY = re.compile(r"\$\$([^$]{1,400})\$\$")
INLINE = re.compile(r"(?<!\$)\$(?!\$)([^$\n]{1,200})\$(?!\$)")
# A formula longer than this is a derivation, not something to search for.
MAX_TEX = 400
# An alignment block is a slice of a worked example, not a formula to look up.
FRAGMENT = re.compile(r"\\(begin|end)\{(aligned|array|align|cases|matrix)")


@dataclass(frozen=True)
class Hit:
    tex: str
    topic: str
    topic_id: int
    context: str


def _context(text: str, start: int, end: int) -> str:
    """The line the formula is on, or what it appears under.

    A display formula almost always sits alone on its line, so its own line says
    nothing once the maths is removed; what a reader needs is the name it appears
    beneath ("Turbine Work, Wt"). The maths is stripped first, then asked whether
    anything readable is left.
    """

    def strip_maths(value: str) -> str:
        value = re.sub(r"\$\$.+?\$\$", " ", value, flags=re.S)
        value = re.sub(r"\$[^$]{1,300}\$", " ", value)
        value = re.sub(r"[*_#>|]+", " ", value)
        return re.sub(r"\s{2,}", " ", value).strip()

    left = text.rfind("\n", 0, max(start - 1, 0))
    right = text.find("\n", end)
    own = strip_maths(text[(left + 1) : right if right != -1 else len(text)])

    if len(own) >= 12:
        return own[:220]

    # The book names its formulas in the line above ("Turbine Work, Wt :"), and
    # that name is what a reader searches for, so it leads the context.
    before = text[:start].strip().splitlines()[-3:]
    names = [strip_maths(item) for item in before if strip_maths(item)]
    return (" ".join(names[-2:]) or own)[:220]


def extract(markdown: str, topic: str, topic_id: int) -> list[Hit]:
    hits: list[Hit] = []
    seen: set[str] = set()
    # Code fences hold worked examples and ASCII sketches; nothing in them is a
    # formula, and matching inside them produces the worst results in the list.
    text = BLOCK.sub(" ", markdown)
    for pattern in (DISPLAY, INLINE):
        for match in pattern.finditer(text):
            raw = match.group(1)
            # A block that wraps is a worked example, not a formula.
            if "\n" in raw.strip():
                continue
            tex = " ".join(raw.split())
            if not tex or len(tex) > MAX_TEX or tex in seen:
                continue
            # A worked example or a table row that happens to contain dollars is
            # not a formula to look up.
            if FRAGMENT.search(tex) or "|" in tex or "**" in tex:
                continue
            # A bare symbol is not a formula: nothing to search for, nothing to
            # read. One operator or command is the bar.
            if not re.search(r"[=<>+\-*/^_\\\\]", tex) or len(tex) < 4:
                continue
            seen.add(tex)
            hits.append(
                Hit(
                    tex=tex,
                    topic=topic,
                    topic_id=topic_id,
                    context=_context(text, match.start(), match.end()),
                )
            )
    return hits


def score(hit: Hit, terms: list[str]) -> int:
    """Every term must appear, in the TeX or the sentence; the count is a rank."""
    haystack = f"{hit.tex} {hit.context} {hit.topic}".lower()
    if not all(term in haystack for term in terms):
        return 0
    return sum(3 if term in hit.tex.lower() else 1 for term in terms)


async def search(db: AsyncSession, query: str, limit: int = 40) -> list[dict]:
    terms = [term for term in re.split(r"\s+", query.strip().lower()) if len(term) > 1]
    if not terms:
        return []

    rows = (
        await db.execute(
            select(TopicPage, TopicPage.topic_id)
            .where(TopicPage.kind.in_(("resources", "reference")))
            .order_by(TopicPage.topic_id)
        )
    ).all()

    names = {topic.id: topic.name for topic in (await db.execute(select(Topic))).scalars()}

    ranked: list[tuple[int, Hit]] = []
    for page, topic_id in rows:
        name = names.get(topic_id, f"topic {topic_id}")
        for hit in extract(page.body, name, topic_id):
            weight = score(hit, terms)
            if weight:
                ranked.append((weight, hit))

    ranked.sort(key=lambda pair: (-pair[0], pair[1].topic, len(pair[1].tex)))
    return [
        {"tex": hit.tex, "topic": hit.topic, "topic_id": hit.topic_id, "context": hit.context}
        for _weight, hit in ranked[:limit]
    ]
