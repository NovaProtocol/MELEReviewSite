from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import Solution


async def get_solution(db: AsyncSession, question_id: int, account_id: int) -> Solution | None:
    result = await db.execute(
        select(Solution).where(Solution.question_id == question_id, Solution.account_id == account_id)
    )
    return result.scalar_one_or_none()


async def upsert_solution(
    db: AsyncSession, question_id: int, account_id: int, convention: str, blocks: str
) -> Solution:
    try:
        parsed = json.loads(blocks)
        if not isinstance(parsed, list):
            raise ValueError("blocks must be a JSON array")
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid blocks JSON: {exc}")

    sol = await get_solution(db, question_id, account_id)
    if sol:
        sol.convention = convention
        sol.blocks = blocks
    else:
        sol = Solution(question_id=question_id, account_id=account_id, convention=convention, blocks=blocks)
        db.add(sol)
    await db.commit()
    await db.refresh(sol)
    return sol


async def delete_solution(db: AsyncSession, question_id: int, account_id: int) -> None:
    sol = await get_solution(db, question_id, account_id)
    if sol:
        await db.delete(sol)
        await db.commit()


async def list_account_solutions(db: AsyncSession, account_id: int) -> list[Solution]:
    result = await db.execute(
        select(Solution).where(Solution.account_id == account_id).order_by(Solution.question_id)
    )
    return list(result.scalars().all())
