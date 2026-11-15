"""A member's numbers, recomputed from the attempt rows.

The counters on ``users`` are a cache. Nothing increments them directly: every
change that could move a number calls one of the ``refresh`` functions and they
recompute from scratch. That is slower than a counter bump and impossible to
drift, which matters more here because a question edit deletes attempt rows in
bulk and a decrement would have to be right about how many.

Four numbers, and the definition of each:

| Field | Meaning |
|---|---|
| ``metric_questions`` | questions this member wrote, hidden ones included |
| ``metric_answered`` | questions they have at least one attempt on |
| ``metric_first_correct`` | of those, how many were right on the first selection |
| ``metric_solved`` | of those, how many have been answered correctly at all |
| ``metric_attempts`` | sum of ``min(attempts, 4)``, which caps the average at 4 |
"""

from __future__ import annotations

from sqlalchemy import Integer, case, cast, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Question, QuestionAttempt, User

# The cap. Someone picking A and B alternately for a hundred presses should read
# as "four tries and still wrong", not as a hundred and a meaningless average.
ATTEMPT_CAP = 4


async def refresh_user(db: AsyncSession, user_id: int) -> None:
    """Recompute one member's cached numbers."""
    questions = int(
        (
            await db.execute(
                select(func.count()).select_from(Question).where(Question.author_user_id == user_id)
            )
        ).scalar_one()
    )
    row = (
        await db.execute(
            select(
                func.count(QuestionAttempt.id),
                # Cast first: SQLite sums a boolean column to a boolean, so an
                # uncased `sum(is_correct)` reported True instead of a count.
                func.coalesce(func.sum(cast(QuestionAttempt.first_correct, Integer)), 0),
                func.coalesce(func.sum(cast(QuestionAttempt.is_correct, Integer)), 0),
                func.coalesce(
                    func.sum(
                        case(
                            (QuestionAttempt.attempts > ATTEMPT_CAP, ATTEMPT_CAP),
                            else_=QuestionAttempt.attempts,
                        )
                    ),
                    0,
                ),
            ).where(QuestionAttempt.user_id == user_id)
        )
    ).one()
    answered, first_correct, solved, attempts = (int(value or 0) for value in row)
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(
            metric_questions=questions,
            metric_answered=answered,
            metric_first_correct=first_correct,
            metric_solved=solved,
            metric_attempts=attempts,
        )
    )


async def refresh_many(db: AsyncSession, user_ids: list[int]) -> None:
    """Recompute for several members at once, de-duplicated."""
    for user_id in {int(user_id) for user_id in user_ids}:
        await refresh_user(db, user_id)


async def clear_attempts_for_question(db: AsyncSession, question_id: int) -> list[int]:
    """Drop every attempt on a question, returning whose numbers moved.

    Called when a question's content is edited or the question is deleted: an
    attempt against a changed problem measured nothing about the current one.
    """
    affected = [
        int(row[0])
        for row in (
            await db.execute(
                select(QuestionAttempt.user_id).where(QuestionAttempt.question_id == question_id)
            )
        ).all()
    ]
    if affected:
        await db.execute(delete(QuestionAttempt).where(QuestionAttempt.question_id == question_id))
    return affected
