from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import media as media_module
from app.auth import require_user
from app.config import get_config
from app.db import get_db
from app.models import Media, User

router = APIRouter(tags=["media"])

UID = re.compile(r"^[0-9a-f]{32}$")


@router.get("/media/{path:path}")
async def serve_media(
    path: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Stream an upload to a signed-in user.

    Uploads are per-visitor content: a solution image is only meant for people who
    are inside the invitation tree, so the route sits behind the session rather
    than behind the static mount.
    """
    # A bare uid is the editor's reference form: `![](/media/<uid>)`. Everything
    # else is a file path, which is how avatars and solutions have always worked.
    if UID.match(path):
        row = (await db.execute(select(Media).where(Media.uid == path))).scalars().first()
        if row is not None:
            resolved = media_module.resolve(get_config().upload_dir, row.path)
            return FileResponse(
                resolved,
                media_type=row.content_type,
                headers={"Cache-Control": "private, no-store"},
            )

    root = get_config().upload_dir
    resolved = media_module.resolve(root, path)
    return FileResponse(
        resolved,
        media_type=media_module.content_type_for(resolved),
        headers={"Cache-Control": "private, no-store"},
    )
