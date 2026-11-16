"""Members reporting something wrong with a question.

The administrator sees the queue, reads the question, and either fixes it or
dismisses the report. A report is not a moderation action: nothing is hidden, and
the question keeps working while it waits.
"""

from __future__ import annotations

import datetime as dt

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Question, QuestionReport, Subject, Topic, User

MAX_REASON = 500


async def report(db: AsyncSession, question: Question, author: User, reason: str) -> QuestionReport:
    text = (reason or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Say what looks wrong")
    if len(text) > MAX_REASON:
        raise HTTPException(status_code=422, detail="Keep it under 500 characters")

    existing = (
        (
            await db.execute(
                select(QuestionReport).where(
                    QuestionReport.question_id == question.id,
                    QuestionReport.reported_by_user_id == author.id,
                    QuestionReport.status == "open",
                )
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="You have already reported this question")

    row = QuestionReport(
        question_id=question.id,
        reported_by_user_id=author.id,
        reason=text,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def has_open_report(db: AsyncSession, question_id: int, user_id: int) -> bool:
    row = (
        (
            await db.execute(
                select(QuestionReport.id).where(
                    QuestionReport.question_id == question_id,
                    QuestionReport.reported_by_user_id == user_id,
                    QuestionReport.status == "open",
                )
            )
        )
        .scalars()
        .first()
    )
    return row is not None


async def open_reports(db: AsyncSession) -> list[dict]:
    rows = (
        await db.execute(
            select(QuestionReport, Question, User.username, Subject.name, Topic.name)
            .join(Question, Question.id == QuestionReport.question_id)
            .join(User, User.id == QuestionReport.reported_by_user_id)
            .join(Topic, Topic.id == Question.topic_id)
            .join(Subject, Subject.id == Topic.subject_id)
            .where(QuestionReport.status == "open")
            .order_by(QuestionReport.date_created)
        )
    ).all()
    return [
        {
            "id": row.id,
            "question_id": question.id,
            "topic_id": question.topic_id,
            "question": question.body,
            "subject": subject,
            "topic": topic,
            "reason": row.reason,
            "reporter": reporter,
            "reported_at": row.date_created,
        }
        for row, question, reporter, subject, topic in rows
    ]


async def resolve(db: AsyncSession, row: QuestionReport, actor: User, action: str) -> dict:
    if action not in {"resolve", "dismiss"}:
        raise HTTPException(status_code=422, detail="Choose resolve or dismiss")
    row.status = "resolved" if action == "resolve" else "dismissed"
    row.resolved_by_user_id = actor.id
    row.resolved_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    await db.commit()
    return {"id": row.id, "status": row.status}


async def open_count(db: AsyncSession) -> int:
    from sqlalchemy import func

    return int(
        (
            await db.execute(
                select(func.count())
                .select_from(QuestionReport)
                .where(QuestionReport.status == "open")
            )
        ).scalar_one()
    )
