"""The two panels a topic carries besides its questions.

Resources is study material, Reference is a sheet of formulas and constants. Both
are Markdown, both are written by someone holding EDIT_TOPIC_CONTENT or by the
system administrator, and both are optional: an empty panel is a valid state.
"""

from __future__ import annotations

import datetime as dt

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import markdown, permissions
from app.models import TopicPage, User

KINDS = ("resources", "reference")
TITLES = {"resources": "Resources", "reference": "Reference"}


def may_edit(user: User | None) -> bool:
    if user is None:
        return False
    return user.is_system_admin or permissions.has(user.permissions, permissions.EDIT_TOPIC_CONTENT)


async def bodies(db: AsyncSession, topic_id: int) -> dict[str, dict]:
    """Both panels for a topic: source, rendered HTML, and who last touched it."""
    rows = (
        (await db.execute(select(TopicPage).where(TopicPage.topic_id == topic_id))).scalars().all()
    )
    found = {row.kind: row for row in rows if row.kind in KINDS}
    out: dict[str, dict] = {}
    for kind in KINDS:
        row = found.get(kind)
        out[kind] = {
            "kind": kind,
            "title": TITLES[kind],
            "body": row.body if row else "",
            "html": markdown.render(row.body) if row else "",
            "updated_at": row.updated_at if row else None,
            "updated_by": row.updated_by_user_id if row else None,
        }
    return out


async def uses_media(db: AsyncSession, uid: str) -> bool:
    """Whether any topic page references this upload.

    A figure dropped into a Resources or Reference panel is not owned by a question
    or a solution, so nothing else would stop the sweep treating it as abandoned.
    """
    row = (
        (
            await db.execute(
                select(TopicPage.id)
                .where(TopicPage.body.like(f"%{uid}%"))
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    return row is not None


async def get(db: AsyncSession, topic_id: int, kind: str) -> TopicPage | None:
    return (
        (
            await db.execute(
                select(TopicPage).where(TopicPage.topic_id == topic_id, TopicPage.kind == kind)
            )
        )
        .scalars()
        .first()
    )


async def save(db: AsyncSession, topic_id: int, kind: str, body: str, actor: User) -> TopicPage:
    if kind not in KINDS:
        raise HTTPException(status_code=404, detail="No such page")
    if not may_edit(actor):
        raise HTTPException(status_code=403, detail="Administrator only")
    row = await get(db, topic_id, kind)
    if row is None:
        row = TopicPage(topic_id=topic_id, kind=kind, body=body or "")
        db.add(row)
    else:
        row.body = body or ""
        row.updated_by_user_id = actor.id
        row.updated_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    await db.commit()
    await db.refresh(row)
    return row
