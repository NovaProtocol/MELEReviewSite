"""Uploaded images and the Markdown preview the editor asks for.

An upload lands on the volume and in the `media` table, and the prose refers to it
as `/media/<uid>`: a path on this site, not a URL on a hostname, so moving to
another domain does not rewrite a single stored question.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import markdown
from app import media as media_module
from app.auth import check_csrf, require_user
from app.config import get_config
from app.db import get_db
from app.models import Media, User

router = APIRouter(prefix="/api", tags=["media"])


class MarkdownBody(BaseModel):
    markdown: str = Field(default="", max_length=20000)


@router.post("/media", status_code=201)
async def upload_media(
    request: Request,
    file: UploadFile,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    config = get_config()
    raw = await media_module.read_upload(file, config.MAX_MEDIA_BYTES)
    detected = media_module.detect(raw)
    assert detected is not None  # read_upload already refused anything else
    content_type, extension = detected

    uid = uuid.uuid4().hex
    relative = await media_module.save_bytes(
        raw, config.upload_dir, "media", config.MAX_MEDIA_BYTES
    )
    # The stored name is random; the uid is the public handle, so rename to it and
    # keep one name for the file and the row.
    final = f"media/{uid}.{extension}"
    source = config.upload_dir / relative
    destination = config.upload_dir / final
    source.replace(destination)

    width, height = media_module.dimensions(raw) or (None, None)
    db.add(
        Media(
            uid=uid,
            path=final,
            content_type=content_type,
            byte_size=len(raw),
            width=width,
            height=height,
            uploaded_by_user_id=user.id,
        )
    )
    await db.commit()
    return {
        "uid": uid,
        "url": f"/media/{uid}",
        "markdown": f"![]({f'/media/{uid}'})",
        "width": width,
        "height": height,
    }


@router.get("/media/{uid}/info")
async def media_info(
    uid: str, user: User = Depends(require_user), db: AsyncSession = Depends(get_db)
):
    row = (await db.execute(select(Media).where(Media.uid == uid))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="No such image")
    return {
        "uid": row.uid,
        "url": f"/media/{row.uid}",
        "width": row.width,
        "height": row.height,
        "byte_size": row.byte_size,
        "question_id": row.question_id,
    }


@router.post("/editor/preview")
async def preview(body: MarkdownBody, user: User = Depends(require_user)):
    """Render Markdown with the same parser the pages use.

    The editor has two modes and needs the Markdown turned into the same HTML the
    reader will see; doing it here means one parser instead of two that drift.
    """
    return {"html": markdown.render(body.markdown)}


async def serve_by_uid(uid: str, db: AsyncSession) -> FileResponse:
    row = (await db.execute(select(Media).where(Media.uid == uid))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    config = get_config()
    resolved = media_module.resolve(config.upload_dir, row.path)
    return FileResponse(
        resolved,
        media_type=row.content_type,
        headers={"Cache-Control": "private, no-store"},
    )
