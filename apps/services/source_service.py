from __future__ import annotations

import hashlib

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.models import Source


async def upload_source(db: AsyncSession, title: str, pdf_bytes: bytes) -> Source:
    pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
    
    existing = await db.execute(select(Source).where(Source.pdf_hash == pdf_hash))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="PDF with this hash already exists")
    
    source = Source(title=title, pdf_blob=pdf_bytes, pdf_hash=pdf_hash)
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


async def list_sources(db: AsyncSession) -> list[Source]:
    result = await db.execute(select(Source).order_by(Source.date_created.desc()))
    return list(result.scalars().all())


async def get_source(db: AsyncSession, source_id: int) -> Source:
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


async def get_source_pdf(db: AsyncSession, source_id: int) -> bytes:
    source = await get_source(db, source_id)
    return source.pdf_blob
