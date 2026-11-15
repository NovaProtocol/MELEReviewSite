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


async def save_bytes(raw: bytes, root: Path, prefix: str, max_bytes: int) -> str:
    """Write bytes that are already in memory, returning the relative path."""
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


async def read_upload(upload: UploadFile, max_bytes: int) -> bytes:
    raw = await upload.read()
    if not raw:
        raise HTTPException(status_code=422, detail="The file is empty")
    if len(raw) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"That image is larger than {max_bytes // (1024 * 1024)} MB",
        )
    if detect(raw) is None:
        raise HTTPException(status_code=422, detail="Upload a PNG, JPEG or WebP image")
    return raw


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


def dimensions(raw: bytes) -> tuple[int, int] | None:
    """The pixel size, read from the header rather than by decoding the image."""
    try:
        if raw.startswith(b"\x89PNG\r\n\x1a\n") and len(raw) >= 24:
            width = int.from_bytes(raw[16:20], "big")
            height = int.from_bytes(raw[20:24], "big")
            return width, height

        if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP" and len(raw) >= 30:
            chunk = raw[12:16]
            if chunk == b"VP8X":
                width = int.from_bytes(raw[24:27], "little") + 1
                height = int.from_bytes(raw[27:30], "little") + 1
                return width, height
            if chunk == b"VP8 ":
                width = int.from_bytes(raw[26:28], "little") & 0x3FFF
                height = int.from_bytes(raw[28:30], "little") & 0x3FFF
                return width, height

        if raw.startswith(b"\xff\xd8"):
            index = 2
            while index + 9 < len(raw):
                if raw[index] != 0xFF:
                    index += 1
                    continue
                marker = raw[index + 1]
                length = int.from_bytes(raw[index + 2 : index + 4], "big")
                if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB}:
                    height = int.from_bytes(raw[index + 5 : index + 7], "big")
                    width = int.from_bytes(raw[index + 7 : index + 9], "big")
                    return width, height
                if length < 2:
                    return None
                index += 2 + length
    except IndexError, ValueError:
        return None
    return None


def content_type_for(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lstrip(".").lower(), "application/octet-stream")


def remove(root: Path, relative: str | None) -> None:
    if not relative:
        return
    with contextlib.suppress(OSError):
        (root / relative).unlink(missing_ok=True)
