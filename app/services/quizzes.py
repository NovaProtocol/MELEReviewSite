"""Saved quizzes: building one, handing it out, and recording sittings.

A quiz used to be a code and nothing else. It is a row now, because it needs an
owner, a visibility, a life and a history of who sat it. The code is still accepted
as an old share link, but the address is `/quiz/<uid>`.

Two rules shape the rest:

- **A first take is permanent.** It is never overwritten, and opening the link
  again shows it rather than starting over. Later sittings are practice: they do
  not replace the score and the sweep deletes them six hours after their last
  update.
- **A quiz whose questions were retired is locked, not rewritten.** The paper still
  shows what was asked; it just cannot be taken again.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import markdown
from app.models import (
    Question,
    QuestionAttempt,
    Quiz,
    QuizQuestion,
    QuizSubmission,
    User,
)
from app.services import metrics

MAX_PER_ACCOUNT = 100
PRACTICE_TTL_HOURS = 6
IDLE_DAYS = 7
DEFAULT_TITLE = "Quiz"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def _answers(raw: str | None) -> dict[str, str]:
    try:
        parsed = json.loads(raw or "{}")
    except ValueError:
        return {}
    return (
        {str(key): str(value) for key, value in parsed.items()} if isinstance(parsed, dict) else {}
    )


async def owned_count(db: AsyncSession, user_id: int) -> int:
    return int(
        (
            await db.execute(
                select(func.count()).select_from(Quiz).where(Quiz.owner_user_id == user_id)
            )
        ).scalar_one()
    )


async def create(
    db: AsyncSession,
    owner: User,
    *,
    title: str,
    description: str,
    settings: dict,
    question_ids: list[int],
    is_private: bool,
    scores_public: bool,
) -> Quiz:
    if not question_ids:
        raise HTTPException(status_code=422, detail="A quiz needs at least one question")
    if await owned_count(db, owner.id) >= MAX_PER_ACCOUNT:
        raise HTTPException(
            status_code=422,
            detail=f"An account can hold {MAX_PER_ACCOUNT} quizzes. Delete one to make room.",
        )
    row = Quiz(
        uid=uuid.uuid4().hex,
        owner_user_id=owner.id,
        title=(title or DEFAULT_TITLE).strip()[:120] or DEFAULT_TITLE,
        description=(description or "").strip() or None,
        settings=json.dumps(settings),
        is_private=is_private,
        scores_public=scores_public,
    )
    db.add(row)
    await db.flush()
    for position, question_id in enumerate(question_ids):
        db.add(QuizQuestion(quiz_id=row.id, position=position, question_id=question_id))
    await db.commit()
    await db.refresh(row)
    return row


async def get(db: AsyncSession, uid: str) -> Quiz:
    row = (await db.execute(select(Quiz).where(Quiz.uid == uid))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="No such quiz")
    return row


def listed(quiz: Quiz, viewer: User | None) -> bool:
    """A private quiz is unlisted, not locked: the link still works.

    Unlisted only hides it from the list. Anyone holding the address can open and
    sit it, which is the point of handing the link out.
    """
    if not quiz.is_private:
        return True
    return viewer is not None and (quiz.owner_user_id == viewer.id or viewer.is_system_admin)


async def questions(db: AsyncSession, quiz: Quiz) -> list[Question]:
    """The paper, in order, including questions that have since been retired."""
    rows = (
        await db.execute(
            select(QuizQuestion.position, Question)
            .join(Question, Question.id == QuizQuestion.question_id)
            .where(QuizQuestion.quiz_id == quiz.id)
            .order_by(QuizQuestion.position)
        )
    ).all()
    return [question for _position, question in rows]


async def positions_with_deleted(db: AsyncSession, quiz: Quiz) -> list[int]:
    rows = (
        await db.execute(
            select(QuizQuestion.position, Question.is_deleted)
            .join(Question, Question.id == QuizQuestion.question_id)
            .where(QuizQuestion.quiz_id == quiz.id)
            .order_by(QuizQuestion.position)
        )
    ).all()
    return [position + 1 for position, deleted in rows if deleted]


async def lock_reason(db: AsyncSession, quiz: Quiz) -> str | None:
    """Why this paper cannot be sat, if it cannot."""
    gone = await positions_with_deleted(db, quiz)
    if gone:
        listed = ", ".join(str(position) for position in gone[:5])
        return f"This quiz is closed: question {listed} was removed from the bank."
    return None


async def touch(db: AsyncSession, quiz: Quiz) -> None:
    quiz.last_activity = _now()
    await db.commit()


async def first_take(db: AsyncSession, quiz: Quiz, user: User) -> QuizSubmission | None:
    return (
        (
            await db.execute(
                select(QuizSubmission).where(
                    QuizSubmission.quiz_id == quiz.id,
                    QuizSubmission.user_id == user.id,
                    QuizSubmission.is_first_take.is_(True),
                )
            )
        )
        .scalars()
        .first()
    )


async def open_sitting(
    db: AsyncSession, quiz: Quiz, user: User, *, practice: bool = False
) -> QuizSubmission:
    """The row this member is answering into.

    A first sitting is created once and reused until it is submitted. Practice
    sittings are new rows every time.
    """
    if not practice:
        existing = await first_take(db, quiz, user)
        if existing is None:
            row = QuizSubmission(quiz_id=quiz.id, user_id=user.id, is_first_take=True)
            db.add(row)
            await db.flush()
        else:
            row = existing
    else:
        row = QuizSubmission(quiz_id=quiz.id, user_id=user.id, is_first_take=False)
        db.add(row)
        await db.flush()
    row.last_seen = _now()
    quiz.last_activity = _now()
    await db.commit()
    await db.refresh(row)
    return row


async def save_progress(
    db: AsyncSession, submission: QuizSubmission, answers: dict[str, str]
) -> None:
    submission.answers = json.dumps(answers)
    submission.last_seen = _now()
    if submission.quiz_id:
        quiz = await db.get(Quiz, submission.quiz_id)
        if quiz is not None:
            quiz.last_activity = _now()
    await db.commit()


def _grade(questions: list[Question], answers: dict[str, str]) -> tuple[int, int]:
    correct = 0
    counted = 0
    for question in questions:
        letter = answers.get(str(question.id))
        if not letter:
            continue
        counted += 1
        if letter == question.correct_choice:
            correct += 1
    return correct, counted


async def submit(
    db: AsyncSession,
    quiz: Quiz,
    submission: QuizSubmission,
    answers: dict[str, str],
    questions: list[Question],
) -> dict:
    """Score a sitting and, for a first take, record the answers as attempts."""
    if submission.submitted_at is not None:
        raise HTTPException(status_code=409, detail="This sitting is already submitted")

    correct, counted = _grade(questions, answers)
    elapsed = int((_now() - submission.started_at).total_seconds())
    submission.answers = json.dumps(answers)
    submission.correct = correct
    submission.total = counted
    submission.score = round(100 * correct / counted) if counted else 0
    submission.duration_seconds = max(elapsed, 0)
    submission.submitted_at = _now()
    submission.last_seen = _now()
    quiz.last_activity = _now()

    if submission.is_first_take:
        await _record_attempts(db, submission.user_id, questions, answers)

    await db.commit()
    await db.refresh(submission)
    results = [
        {
            "question_id": question.id,
            "topic_id": question.topic_id,
            "chosen": answers.get(str(question.id)),
            "correct_choice": question.correct_choice,
            "correct": answers.get(str(question.id)) == question.correct_choice,
        }
        for question in questions
    ]
    return {
        "score": submission.score,
        "correct": correct,
        "total": counted,
        "duration_seconds": submission.duration_seconds,
        "is_first_take": submission.is_first_take,
        "results": results,
    }


async def _record_attempts(
    db: AsyncSession, user_id: int, questions: list[Question], answers: dict[str, str]
) -> None:
    """A first take counts as answering, exactly like the question page."""
    existing = {
        attempt.question_id: attempt
        for attempt in (
            await db.execute(
                select(QuestionAttempt).where(
                    QuestionAttempt.user_id == user_id,
                    QuestionAttempt.question_id.in_([q.id for q in questions]),
                )
            )
        )
        .scalars()
        .all()
    }
    for question in questions:
        letter = answers.get(str(question.id))
        if not letter:
            continue
        row = existing.get(question.id)
        if row is not None and row.is_correct:
            continue
        is_correct = letter == question.correct_choice
        if row is None:
            db.add(
                QuestionAttempt(
                    question_id=question.id,
                    user_id=user_id,
                    chosen=letter,
                    first_selection=letter,
                    first_correct=is_correct,
                    is_correct=is_correct,
                    attempts=1,
                )
            )
        else:
            row.chosen = letter
            row.is_correct = row.is_correct or is_correct
            row.attempts = max(int(row.attempts or 0), 1) + 1
    await db.flush()
    await metrics.refresh_user(db, user_id)


async def submissions_for(db: AsyncSession, quiz: Quiz) -> list[dict]:
    """Everyone's sittings, for the owner and the administrator."""
    rows = (
        await db.execute(
            select(QuizSubmission, User.username, User.uid)
            .join(User, User.id == QuizSubmission.user_id)
            .where(QuizSubmission.quiz_id == quiz.id)
            .order_by(QuizSubmission.is_first_take.desc(), QuizSubmission.score.desc())
        )
    ).all()
    return [
        {
            "id": row.id,
            "user": username,
            "user_uid": uid,
            "is_first_take": row.is_first_take,
            "score": row.score,
            "correct": row.correct,
            "total": row.total,
            "duration_seconds": row.duration_seconds,
            "submitted": row.submitted_at is not None,
            "last_seen": row.last_seen,
        }
        for row, username, uid in rows
    ]


async def leaderboard(db: AsyncSession, quiz: Quiz, limit: int = 20) -> list[dict]:
    """Best first take per member: the board people are actually competing on."""
    rows = (
        await db.execute(
            select(QuizSubmission, User.username)
            .join(User, User.id == QuizSubmission.user_id)
            .where(
                QuizSubmission.quiz_id == quiz.id,
                QuizSubmission.is_first_take.is_(True),
                QuizSubmission.submitted_at.is_not(None),
            )
            .order_by(
                QuizSubmission.score.desc(),
                QuizSubmission.duration_seconds.asc(),
                QuizSubmission.submitted_at.asc(),
            )
            .limit(limit)
        )
    ).all()
    return [
        {
            "user": username,
            "score": row.score,
            "correct": row.correct,
            "total": row.total,
            "duration_seconds": row.duration_seconds,
        }
        for row, username in rows
    ]


async def remove(db: AsyncSession, quiz: Quiz, actor: User) -> None:
    """Permanent, and it takes every sitting with it."""
    if quiz.owner_user_id != actor.id and not actor.is_system_admin:
        raise HTTPException(status_code=403, detail="Not your quiz")
    await db.execute(delete(QuizSubmission).where(QuizSubmission.quiz_id == quiz.id))
    await db.execute(delete(QuizQuestion).where(QuizQuestion.quiz_id == quiz.id))
    await db.delete(quiz)
    await db.commit()


async def remove_for_owner(db: AsyncSession, user_id: int) -> int:
    """Used when a member is banned: their quizzes go, their questions stay."""
    rows = (await db.execute(select(Quiz).where(Quiz.owner_user_id == user_id))).scalars().all()
    for quiz in rows:
        await db.execute(delete(QuizSubmission).where(QuizSubmission.quiz_id == quiz.id))
        await db.execute(delete(QuizQuestion).where(QuizQuestion.quiz_id == quiz.id))
        await db.delete(quiz)
    await db.commit()
    return len(rows)


async def clear_attempt(db: AsyncSession, quiz: Quiz, user_id: int) -> int:
    """The administrator's escape hatch: forget one member's sitting."""
    result = await db.execute(
        delete(QuizSubmission).where(
            QuizSubmission.quiz_id == quiz.id, QuizSubmission.user_id == user_id
        )
    )
    await db.commit()
    return result.rowcount or 0


async def sweep(db: AsyncSession, now: dt.datetime | None = None) -> dict:
    """Practice sittings expire; idle quizzes become private."""
    moment = now or _now()
    cutoff = moment - dt.timedelta(hours=PRACTICE_TTL_HOURS)
    expired = await db.execute(
        delete(QuizSubmission).where(
            QuizSubmission.is_first_take.is_(False), QuizSubmission.last_seen < cutoff
        )
    )
    idle_cutoff = moment - dt.timedelta(days=IDLE_DAYS)
    privatised = await db.execute(
        select(Quiz).where(Quiz.is_private.is_(False), Quiz.last_activity < idle_cutoff)
    )
    rows = privatised.scalars().all()
    for quiz in rows:
        quiz.is_private = True
    await db.commit()
    return {"practice_removed": expired.rowcount or 0, "privatised": len(rows)}


async def listing(db: AsyncSession, viewer: User, scope: str = "all") -> list[dict]:
    """The quizzes a page can show: public ones, plus the viewer's own."""
    query = select(Quiz, User.username, User.uid).join(User, User.id == Quiz.owner_user_id)
    if scope == "mine":
        query = query.where(Quiz.owner_user_id == viewer.id)
    query = query.order_by(Quiz.last_activity.desc()).limit(200)
    rows = (await db.execute(query)).all()

    out = []
    for quiz, owner, owner_uid in rows:
        if quiz.is_private and not (quiz.owner_user_id == viewer.id or viewer.is_system_admin):
            continue
        count = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(QuizQuestion)
                    .where(QuizQuestion.quiz_id == quiz.id)
                )
            ).scalar_one()
        )
        mine = await first_take(db, quiz, viewer)
        out.append(
            {
                "uid": quiz.uid,
                "title": quiz.title,
                "description": quiz.description,
                "owner": owner,
                "owner_uid": owner_uid,
                "is_private": quiz.is_private,
                "is_mine": quiz.owner_user_id == viewer.id,
                "questions": count,
                "date_created": quiz.date_created,
                "last_activity": quiz.last_activity,
                "taken": bool(mine and mine.submitted_at),
                "my_score": mine.score if mine and mine.submitted_at else None,
            }
        )
    return out


def plain(text: str | None, limit: int = 180) -> str:
    return markdown.to_plain(text or "", limit)
