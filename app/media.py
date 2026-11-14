"""Uploaded images on disk.

The database stores a relative path, never the bytes: a phone photo is 4 to 8 MB,
which is larger than the packets MySQL accepts by default, would sit in memory
while being read back, and would inflate every database backup. The files live on
their own volume, so a future tool that cleans or re-encodes them rewrites files in
place without a schema change.

Type detection is by magic bytes rather than the client's content type, because the
content type is whatever the client decides to send.
"""

from __future__ import annotations

import contextlib
import os
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

SIGNATURES: tuple[tuple[bytes, str, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"RIFF", "image/webp", "webp"),
)

CONTENT_TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}


def detect(raw: bytes) -> tuple[str, str] | None:
    if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "image/webp", "webp"
    for signature, mime, extension in SIGNATURES:
        if signature == b"RIFF":
            continue
        if raw.startswith(signature):
            return mime, extension
    return None


async def save(upload: UploadFile, root: Path, prefix: str, max_bytes: int) -> str:
    """Write one upload and return its relative path.

    Files are grouped by prefix so a directory listing is readable, and named by a
    fresh uuid so nothing collides or leaks the uploader's filename.
    """
    raw = await upload.read()
    if not raw:
        raise HTTPException(status_code=422, detail="The file is empty")
    if len(raw) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"That image is larger than {max_bytes // (1024 * 1024)} MB",
        )
    detected = detect(raw)
    if detected is None:
        raise HTTPException(status_code=422, detail="Upload a PNG, JPEG or WebP image")
    _mime, extension = detected
    relative = f"{prefix}/{uuid.uuid4().hex}.{extension}"
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(raw)
    os.replace(temporary, destination)
    return relative


def resolve(root: Path, relative: str) -> Path:
    """Resolve a stored path, refusing anything that escapes the upload root."""
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise HTTPException(status_code=404, detail="Not found")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return candidate


def content_type_for(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lstrip(".").lower(), "application/octet-stream")


def remove(root: Path, relative: str | None) -> None:
    if not relative:
        return
    with contextlib.suppress(OSError):
        (root / relative).unlink(missing_ok=True)
