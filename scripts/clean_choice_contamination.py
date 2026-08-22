"""Clean contaminated choice_d values: truncate at junk markers, strip garbage glyphs."""

from __future__ import annotations

import asyncio
import logging
import re

from sqlalchemy import or_, select

from api.db import _get_session_factory
from api.models import Question

logger = logging.getLogger("melereview-clean")

MARKERS = [" Solution:", " Note:", " NOTE:", " Ans.", " LET ", " Using Moody", " Given"]


def clean(value: str | None) -> tuple[str | None, bool]:
    """Truncate choice_d at junk markers and strip Symbol garbage."""
    if not value:
        return value, False
    out = value
    for m in MARKERS:
        idx = out.find(m)
        if idx > 0:
            out = out[:idx]
    # Strip Symbol private-use glyphs and stray math junk
    out = re.sub(r"[\uf000-\uf0ff]", "", out)
    out = re.sub(r"\s+", " ", out).strip()
    out = out.strip(" \uf020\uf0e6\uf0f7\uf0f8\uf0f6\uf0e7\uf0e8")
    return out, out != value


async def main() -> None:
    """Clean contaminated choice_d rows in DB. Logs count and commits."""
    async with _get_session_factory()() as db:
        r = await db.execute(
            select(Question).where(
                or_(
                    Question.choice_d.like("%Solution:%"),
                    Question.choice_d.like("%Note:%"),
                )
            )
        )
        rows = r.scalars().all()
        changed = 0
        for q in rows:
            nd, did = clean(q.choice_d)
            if did:
                q.choice_d = nd
                changed += 1
        await db.commit()
        # Use logging per §8 — no print in scripts
        logger.info("cleaned %s rows", changed)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(main())
