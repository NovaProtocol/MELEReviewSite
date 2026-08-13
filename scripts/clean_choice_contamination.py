"""Clean contaminated choice_d values: truncate at junk markers, strip garbage glyphs."""
import asyncio
import re
from apps.db import _get_session_factory
from apps.models import Question
from sqlalchemy import select, or_

MARKERS = [' Solution:', ' Note:', ' NOTE:', ' Ans.', ' LET ', ' Using Moody', ' Given']

def clean(value):
    if not value:
        return value, False
    out = value
    for m in MARKERS:
        idx = out.find(m)
        if idx > 0:
            out = out[:idx]
    # strip private-use-area glyphs (Symbol font garbage) and stray unicode math junk
    before = out
    out = re.sub(r'[\uf000-\uf0ff]', '', out)
    out = re.sub(r'\s+', ' ', out).strip()
    out = out.strip(' \uf020\uf0e6\uf0f7\uf0f8\uf0f6\uf0e7\uf0e8')
    return out, out != value

async def main():
    async with _get_session_factory()() as db:
        r = await db.execute(select(Question).where(or_(
            Question.choice_d.like('%Solution:%'),
            Question.choice_d.like('%Note:%'),
        )))
        rows = r.scalars().all()
        changed = 0
        for q in rows:
            nd, did = clean(q.choice_d)
            if did:
                q.choice_d = nd
                changed += 1
        await db.commit()
        print(f"cleaned {changed} rows")

asyncio.run(main())
