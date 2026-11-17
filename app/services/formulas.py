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

DISPLAY = re.compile(r"\$\$(.+?)\$\$", re.S)
INLINE = re.compile(r"(?<!\$)\$(?!\$)([^$\n]{1,400})\$(?!\$)")
# A formula longer than this is a derivation, not something to search for.
MAX_TEX = 400


@dataclass(frozen=True)
class Hit:
    tex: str
    topic: str
    topic_id: int
    context: str


def _context(text: str, start: int, end: int) -> str:
    left = text.rfind("\n", 0, max(start - 1, 0))
    right = text.find("\n", end)
    line = text[(left + 1) : right if right != -1 else len(text)].strip()
    line = re.sub(r"\$\$.+?\$\$", " ", line, flags=re.S)
    line = re.sub(r"\$[^$]{1,200}\$", " ", line)
    line = re.sub(r"[*_#>|]+", " ", line)
    line = re.sub(r"\s{2,}", " ", line).strip()
    return line[:220]


def extract(markdown: str, topic: str, topic_id: int) -> list[Hit]:
    hits: list[Hit] = []
    seen: set[str] = set()
    for pattern in (DISPLAY, INLINE):
        for match in pattern.finditer(markdown):
            tex = match.group(1).strip()
            if not tex or len(tex) > MAX_TEX or tex in seen:
                continue
            seen.add(tex)
            hits.append(
                Hit(
                    tex=tex,
                    topic=topic,
                    topic_id=topic_id,
                    context=_context(markdown, match.start(), match.end()),
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
