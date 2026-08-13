from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from apps.db import get_db
from apps.models import Solution

router = APIRouter(prefix="/api")


class SolutionUpdate(BaseModel):
    blocks: str
    convention: str = "metric"


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
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Solution).where(Solution.question_id == question_id)
    )
    sol = result.scalar_one_or_none()
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
