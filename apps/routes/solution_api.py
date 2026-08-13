from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from apps.db import get_db
from apps.models import Solution
from apps.routes.api import verify_write_access

router = APIRouter(prefix="/api")


class SolutionUpdate(BaseModel):
    blocks: str = Field(..., max_length=100000)
    convention: str = Field(default="metric", max_length=20)


class SolutionOut(BaseModel):
    id: int
    question_id: int
    convention: str
    blocks: str


@router.get("/questions/{question_id}/solution")
async def get_solution(question_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Solution).where(Solution.question_id == question_id)
    )
    sol = result.scalar_one_or_none()
    if sol:
        return SolutionOut(
            id=sol.id, question_id=sol.question_id,
            convention=sol.convention, blocks=sol.blocks,
        )
    return {"id": None, "question_id": question_id, "convention": "metric", "blocks": "[]"}


@router.put("/questions/{question_id}/solution")
async def upsert_solution(
    question_id: int,
    body: SolutionUpdate,
    _: str = Depends(verify_write_access),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Solution).where(Solution.question_id == question_id)
    )
    sol = result.scalar_one_or_none()

    try:
        parsed = json.loads(body.blocks)
        if not isinstance(parsed, list):
            raise ValueError("blocks must be a JSON array")
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid blocks JSON: {exc}")

    if sol:
        sol.blocks = body.blocks
        sol.convention = body.convention
    else:
        sol = Solution(
            question_id=question_id,
            blocks=body.blocks,
            convention=body.convention,
        )
        db.add(sol)
    await db.commit()
    await db.refresh(sol)
    return SolutionOut(
        id=sol.id, question_id=sol.question_id,
        convention=sol.convention, blocks=sol.blocks,
    )
