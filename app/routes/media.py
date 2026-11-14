from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app import media as media_module
from app.auth import require_user
from app.config import get_config
from app.models import User

router = APIRouter(tags=["media"])


@router.get("/media/{path:path}")
async def serve_media(path: str, user: User = Depends(require_user)) -> FileResponse:
    """Stream an upload to a signed-in user.

    Uploads are per-visitor content: a solution image is only meant for people who
    are inside the invitation tree, so the route sits behind the session rather
    than behind the static mount.
    """
    root = get_config().upload_dir
    resolved = media_module.resolve(root, path)
    return FileResponse(
        resolved,
        media_type=media_module.content_type_for(resolved),
        headers={"Cache-Control": "private, no-store"},
    )
