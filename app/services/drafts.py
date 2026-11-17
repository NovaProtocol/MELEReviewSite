"""A member's own scratchpad for one question.

The editor on a question page is for working out an answer. Most of the time that
working is private: a half-finished attempt, a sketch, a reminder of where they got
stuck. Only when they tick "mark as solution" does it become something other people
can read.

That is a second thing per (member, question), not a second solution: a member can
have both a private note and a published solution for the same question, and
un-ticking the box must not destroy the text.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import QuestionDraft


async def read(db: AsyncSession, question_id: int, user_id: int) -> str:
    row = (
        (
            await db.execute(
                select(QuestionDraft).where(
                    QuestionDraft.question_id == question_id,
                    QuestionDraft.user_id == user_id,
                )
            )
        )
        .scalars()
        .first()
    )
    return row.body if row else ""


async def save(db: AsyncSession, question_id: int, user_id: int, body: str) -> None:
    row = (
        (
            await db.execute(
                select(QuestionDraft).where(
                    QuestionDraft.question_id == question_id,
                    QuestionDraft.user_id == user_id,
                )
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        if not body.strip():
            return
        db.add(QuestionDraft(question_id=question_id, user_id=user_id, body=body))
    else:
        row.body = body
    await db.commit()
