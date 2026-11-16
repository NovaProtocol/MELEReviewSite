"""A member's numbers, recomputed from the attempt rows.

The counters on ``users`` are a cache. Nothing increments them directly: every
change that could move a number calls one of the ``refresh`` functions and they
recompute from scratch. That is slower than a counter bump and impossible to
drift, which matters more here because a question edit deletes attempt rows in
bulk and a decrement would have to be right about how many.

Four numbers, and the definition of each:

| Field | Meaning |
|---|---|
| ``metric_questions`` | questions this member wrote, hidden ones included, deleted ones excluded |
| ``metric_answered`` | questions they have at least one attempt on, deleted ones excluded |
| ``metric_first_correct`` | of those, how many were right on the first selection |
| ``metric_solved`` | of those, how many have been answered correctly at all |
| ``metric_attempts`` | sum of ``min(attempts, 4)``, which caps the average at 4 |
"""

from __future__ import annotations

from sqlalchemy import Integer, case, cast, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Question, QuestionAttempt, Subject, Topic, User

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
            )
            .join(Question, Question.id == QuestionAttempt.question_id)
            # A deleted question no longer measures anything about this member,
            # which is what "deleted doesn't count towards metrics" means.
            .where(
                QuestionAttempt.user_id == user_id,
                Question.is_deleted.is_(False),
            )
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


async def refresh_all_for_question(db: AsyncSession, question_id: int) -> None:
    """Refresh every member who has attempted a question.

    Called when a question is deleted or restored: whether it counts towards a
    member's numbers just changed, and every affected row has to agree.
    """
    user_ids = [
        int(row[0])
        for row in (
            await db.execute(
                select(QuestionAttempt.user_id).where(QuestionAttempt.question_id == question_id)
            )
        ).all()
    ]
    await refresh_many(db, user_ids)


async def topic_mastery(db: AsyncSession, user_id: int) -> dict:
    """Where this member is strong and where they are not, topic by topic.

    One aggregate over the attempt rows, grouped by the topic the question sits
    in. Topics with no attempts are left out: an empty row says nothing, and the
    page is about what has actually been tried.

    Rates are computed here rather than stored, because a per-topic cache would
    have to be invalidated on every edit that deletes attempts.
    """
    rows = (
        await db.execute(
            select(
                Topic.id,
                Topic.name,
                Subject.name,
                func.count(QuestionAttempt.id),
                func.coalesce(func.sum(cast(QuestionAttempt.is_correct, Integer)), 0),
                func.coalesce(func.sum(cast(QuestionAttempt.first_correct, Integer)), 0),
            )
            .join(Question, Question.id == QuestionAttempt.question_id)
            .join(Topic, Topic.id == Question.topic_id)
            .join(Subject, Subject.id == Topic.subject_id)
            .where(
                QuestionAttempt.user_id == user_id,
                Question.is_deleted.is_(False),
                Question.is_hidden.is_(False),
            )
            .group_by(Topic.id, Topic.name, Subject.name)
        )
    ).all()

    topics = []
    subjects: dict[str, dict] = {}
    for topic_id, topic, subject, answered, solved, first_correct in rows:
        answered = int(answered)
        entry = {
            "topic_id": topic_id,
            "topic": topic,
            "subject": subject,
            "answered": answered,
            "solved": int(solved),
            "first_correct": int(first_correct),
            "accuracy": round(100 * int(solved) / answered) if answered else 0,
            "first_try_rate": round(100 * int(first_correct) / answered) if answered else 0,
        }
        topics.append(entry)
        bucket = subjects.setdefault(
            subject, {"subject": subject, "answered": 0, "solved": 0, "first_correct": 0}
        )
        bucket["answered"] += answered
        bucket["solved"] += int(solved)
        bucket["first_correct"] += int(first_correct)

    for bucket in subjects.values():
        answered = bucket["answered"]
        bucket["accuracy"] = round(100 * bucket["solved"] / answered) if answered else 0
        bucket["first_try_rate"] = (
            round(100 * bucket["first_correct"] / answered) if answered else 0
        )

    topics.sort(key=lambda item: (item["subject"], -item["answered"]))
    return {
        "topics": topics,
        "subjects": sorted(subjects.values(), key=lambda item: item["subject"]),
        "answered": sum(item["answered"] for item in topics),
    }
