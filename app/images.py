"""Preparing an upload for storage.

Two things happen to a picture before it is written: it is shrunk to a sane
maximum edge, and it is re-encoded, which drops the EXIF block. A phone photo
carries its location in that block, and a 2400x3000 photo is a great deal of
network for a diagram that will be shown 600 pixels wide.

A picture that is already small and carries no metadata is stored exactly as it
arrived: re-encoding it would cost quality for nothing.
"""

from __future__ import annotations

import io

from PIL import Image, UnidentifiedImageError

# What Pillow is allowed to re-save, mapped to the extension already used on disk.
_FORMATS = {
    "PNG": ("image/png", "png"),
    "JPEG": ("image/jpeg", "jpg"),
    "WEBP": ("image/webp", "webp"),
}


def _save(image: Image.Image, fmt: str) -> bytes:
    buffer = io.BytesIO()
    if fmt == "JPEG":
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        image.save(buffer, "JPEG", quality=85, optimize=True, progressive=True)
    elif fmt == "WEBP":
        image.save(buffer, "WEBP", quality=85, method=4)
    else:
        image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def normalise(raw: bytes, max_edge: int) -> tuple[bytes, str, str, int, int]:
    """Return (bytes, content type, extension, width, height) ready to store."""
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except UnidentifiedImageError, OSError:
        # Not something Pillow understands; the caller's magic-byte check already
        # decided it is an image, so pass it through rather than fail the upload.
        return raw, "", "", 0, 0

    fmt = (image.format or "").upper()
    if fmt not in _FORMATS:
        return raw, "", "", image.width, image.height

    content_type, extension = _FORMATS[fmt]
    oversized = max(image.size) > max_edge
    carries_metadata = bool(image.info.get("exif")) or bool(image.info.get("icc_profile"))

    if not oversized and not carries_metadata:
        return raw, content_type, extension, image.width, image.height

    original_width, original_height = image.size
    if oversized:
        image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)

    # Re-encoding writes a fresh file with no EXIF: that is the point.
    prepared = _save(image, fmt)
    if len(prepared) >= len(raw) and not carries_metadata:
        # Shrinking made it bigger, which happens with small already-compressed
        # images. Keep the original bytes, and report the size they really are.
        return raw, content_type, extension, original_width, original_height
    return prepared, content_type, extension, image.width, image.height
