"""A member's workspace arrangement, kept so it travels with them.

The browser holds its own copy for the first paint; this is the copy that crosses
machines. The merge is by timestamp and nothing else: whoever edited last owns the
arrangement. A layout restored from the server is old even though it has just
arrived, which is why the client's stamp is stored rather than the row's mtime.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import WorkspaceLayout

MAX_BODY = 400_000


async def read(db: AsyncSession, user_id: int) -> dict | None:
    row = await db.get(WorkspaceLayout, user_id)
    if row is None:
        return None
    return {"layout": row.body, "saved_at": row.saved_at}


async def save(db: AsyncSession, user_id: int, body: str, saved_at: int) -> dict:
    """Store an arrangement, unless the server already holds a newer one.

    Refusing a stale write is the whole point: a second browser left open on an old
    layout must not overwrite the one built since.
    """
    if len(body) > MAX_BODY:
        raise ValueError("layout too large")

    row = await db.get(WorkspaceLayout, user_id)
    if row is None:
        row = WorkspaceLayout(user_id=user_id, body=body, saved_at=saved_at)
        db.add(row)
        await db.commit()
        return {"layout": row.body, "saved_at": row.saved_at}

    if saved_at <= row.saved_at:
        # The server is newer or the same: hand it back so the client can adopt it.
        return {"layout": row.body, "saved_at": row.saved_at, "rejected": True}

    row.body = body
    row.saved_at = saved_at
    await db.commit()
    return {"layout": row.body, "saved_at": row.saved_at}
