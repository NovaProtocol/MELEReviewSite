from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.db import get_db
from api.models import Account
from api.routes.auth import get_current_account
from api.schemas import SolutionOut, SolutionWithAccount, SolutionWrite
from api.services import question_service, solution_service

router = APIRouter(prefix="/api", tags=["solutions"])


@router.get("/questions/{question_id}/solution", response_model=SolutionOut | None)
async def get_solution(
    question_id: int,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    # Ensure question exists, 404 if gone
    await question_service.get_question(db, question_id)
    return await solution_service.get_solution(db, question_id, account.id)


@router.get("/my/solutions", response_model=list[SolutionOut])
async def my_solutions(
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    return await solution_service.list_account_solutions(db, account.id)


@router.put("/questions/{question_id}/solution", response_model=SolutionOut)
async def upsert_solution(
    question_id: int,
    body: SolutionWrite,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    # Ensure question exists, 404 if gone
    await question_service.get_question(db, question_id)
    return await solution_service.upsert_solution(
        db, question_id, account.id, body.convention, body.blocks
    )


@router.delete("/questions/{question_id}/solution", status_code=204)
async def delete_solution(
    question_id: int,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    await solution_service.delete_solution(db, question_id, account.id)


@router.get("/questions/{question_id}/solutions", response_model=list[SolutionWithAccount])
async def list_solutions_for_question(
    question_id: int,
    db: AsyncSession = Depends(get_db),
):
    await question_service.get_question(db, question_id)
    return await solution_service.list_solutions_for_question(db, question_id)
