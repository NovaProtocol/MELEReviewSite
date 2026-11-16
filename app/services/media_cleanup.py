"""Deleting uploads nothing refers to.

An image uploaded in the editor is written before the question exists, so there
are two ways it can end up unused: the edit was abandoned, or a later edit removed
it. Both are space that buys nothing.

The rule is the same in both paths: a row that no question claims may go. Saving
deletes what that question just released, and a sweep at startup clears anything
left over after a grace period, so an edit still open in a tab is never pulled
from under its author.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import media as media_module
from app.models import Media

logger = logging.getLogger("melereview.media")


async def remove_paths(root: Path, paths: list[str]) -> None:
    for relative in paths:
        media_module.remove(root, relative)


async def sweep(
    db: AsyncSession, root: Path, grace_hours: int, now: dt.datetime | None = None
) -> int:
    """Delete uploads no question has claimed after the grace period."""
    moment = now or dt.datetime.now(dt.UTC).replace(tzinfo=None)
    cutoff = moment - dt.timedelta(hours=max(grace_hours, 0))
    rows = (
        (
            await db.execute(
                select(Media).where(Media.question_id.is_(None), Media.date_created < cutoff)
            )
        )
        .scalars()
        .all()
    )
    paths = [row.path for row in rows]
    for row in rows:
        await db.delete(row)
    if rows:
        await db.commit()
    await remove_paths(root, paths)
    return len(rows)


async def run_periodically(interval_hours: int, grace_hours: int) -> None:
    """Sweep on a timer, so uploads do not wait for the next restart.

    The startup sweep only runs when the process does. A site that stays up for a
    month would collect a month of abandoned uploads before clearing them.
    """
    from app.config import get_config
    from app.db import _get_session_factory

    interval = max(int(interval_hours), 1) * 3600
    while True:
        await asyncio.sleep(interval)
        try:
            factory = _get_session_factory()
            async with factory() as session:
                removed = await sweep(session, get_config().upload_dir, grace_hours)
            if removed:
                logger.info("media sweep removed %s unused uploads", removed)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("media sweep failed; will try again next interval")
