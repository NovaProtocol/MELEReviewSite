"""Subjects, topics, and the public question read path.

Visibility is decided in one place: a question is public when it is not hidden
and its author is active. A ban therefore hides a user's whole history without
rewriting a single content row, and restoring the account brings it back.
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app import permissions
from app.models import (
    Question,
    QuestionAttempt,
    QuestionFlag,
    Solution,
    Subject,
    Topic,
    User,
)

LETTERS = ("A", "B", "C", "D", "E")


def _public_question_filter():
    return (Question.is_hidden.is_(False), User.status == "active")


def _public_solution_filter():
    return (Solution.is_hidden.is_(False), User.status == "active")


async def list_subjects(db: AsyncSession) -> list[dict]:
    subject_rows = (
        (await db.execute(select(Subject).order_by(Subject.display_order, Subject.name)))
        .scalars()
        .all()
    )
    topic_rows = (
        await db.execute(
            select(Topic, func.count(Question.id))
            .outerjoin(
                Question,
                (Question.topic_id == Topic.id) & Question.is_hidden.is_(False),
            )
            .where(Topic.is_active.is_(True))
            .group_by(Topic.id)
            .order_by(Topic.display_order, Topic.name)
        )
    ).all()
    grouped: dict[int, list[dict]] = {}
    for topic, count in topic_rows:
        grouped.setdefault(topic.subject_id, []).append(
            {
                "id": topic.id,
                "name": topic.name,
                "questions": int(count),
                "is_active": topic.is_active,
            }
        )
    return [
        {
            "id": subject.id,
            "name": subject.name,
            "topics": grouped.get(subject.id, []),
        }
        for subject in subject_rows
    ]


async def get_topic(db: AsyncSession, topic_id: int) -> tuple[Topic, Subject]:
    topic = await db.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    subject = await db.get(Subject, topic.subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    return topic, subject


async def list_topics(db: AsyncSession, subject_id: int | None = None) -> list[Topic]:
    stmt = select(Topic).order_by(Topic.display_order, Topic.name)
    if subject_id is not None:
        stmt = stmt.where(Topic.subject_id == subject_id)
    return list((await db.execute(stmt)).scalars().all())


async def create_subject(db: AsyncSession, name: str) -> Subject:
    clean = name.strip()
    if not clean:
        raise HTTPException(status_code=422, detail="Name is required")
    exists = (await db.execute(select(Subject).where(Subject.name == clean))).scalars().first()
    if exists is not None:
        raise HTTPException(status_code=409, detail="That subject already exists")
    highest = (await db.execute(select(func.max(Subject.display_order)))).scalar() or 0
    subject = Subject(name=clean, display_order=int(highest) + 1)
    db.add(subject)
    await db.commit()
    await db.refresh(subject)
    return subject


async def rename_subject(db: AsyncSession, subject_id: int, name: str) -> Subject:
    subject = await db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    clean = name.strip()
    if not clean:
        raise HTTPException(status_code=422, detail="Name is required")
    subject.name = clean
    await db.commit()
    await db.refresh(subject)
    return subject


async def create_topic(db: AsyncSession, subject_id: int, name: str) -> Topic:
    subject = await db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    clean = name.strip()
    if not clean:
        raise HTTPException(status_code=422, detail="Name is required")
    clash = (
        (await db.execute(select(Topic).where(Topic.subject_id == subject_id, Topic.name == clean)))
        .scalars()
        .first()
    )
    if clash is not None:
        raise HTTPException(status_code=409, detail="That topic already exists")
    highest = (
        await db.execute(
            select(func.max(Topic.display_order)).where(Topic.subject_id == subject_id)
        )
    ).scalar() or 0
    topic = Topic(subject_id=subject_id, name=clean, display_order=int(highest) + 1)
    db.add(topic)
    await db.commit()
    await db.refresh(topic)
    return topic


async def set_topic_active(db: AsyncSession, topic_id: int, is_active: bool) -> Topic:
    topic = await db.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    topic.is_active = is_active
    await db.commit()
    await db.refresh(topic)
    return topic


async def question_view(
    db: AsyncSession,
    question: Question,
    viewer: User | None = None,
    *,
    include_hidden: bool = False,
) -> dict:
    author = await db.get(User, question.author_user_id)
    solutions = []
    solution_rows = (
        await db.execute(
            select(Solution, User.username, User.uid, User.status)
            .join(User, User.id == Solution.author_user_id)
            .where(Solution.question_id == question.id)
            .order_by(Solution.date_created)
        )
    ).all()
    for solution, username, uid, author_status in solution_rows:
        if solution.is_hidden and not include_hidden:
            continue
        if author_status != "active" and not include_hidden:
            continue
        solutions.append(
            {
                "id": solution.id,
                "image_url": f"/media/{solution.image_path}",
                "note": solution.note,
                "author": username,
                "author_uid": uid,
                "is_hidden": solution.is_hidden,
                "date_created": solution.date_created,
            }
        )
    attempt = None
    bookmarked = False
    if viewer is not None:
        attempt_row = (
            (
                await db.execute(
                    select(QuestionAttempt).where(
                        QuestionAttempt.question_id == question.id,
                        QuestionAttempt.user_id == viewer.id,
                    )
                )
            )
            .scalars()
            .first()
        )
        if attempt_row is not None:
            attempt = {"chosen": attempt_row.chosen, "is_correct": attempt_row.is_correct}
        bookmarked = (
            await db.execute(
                select(QuestionFlag.id).where(
                    QuestionFlag.question_id == question.id,
                    QuestionFlag.user_id == viewer.id,
                )
            )
        ).scalars().first() is not None
    return {
        "id": question.id,
        "body": question.body,
        "choices": {
            "A": question.choice_a,
            "B": question.choice_b,
            "C": question.choice_c,
            "D": question.choice_d,
            "E": question.choice_e,
        },
        "correct_choice": question.correct_choice,
        "explanation": question.explanation,
        "is_hidden": question.is_hidden,
        "author": author.username if author else None,
        "author_uid": author.uid if author else None,
        "author_status": author.status if author else None,
        "solutions": solutions,
        "attempt": attempt,
        "bookmarked": bookmarked,
        "date_created": question.date_created,
    }


async def list_questions(
    db: AsyncSession,
    topic_id: int,
    search: str = "",
    bookmarked_by: User | None = None,
    include_hidden: bool = False,
    viewer: User | None = None,
    per_page: int = 200,
) -> list[dict]:
    stmt = (
        select(Question)
        .join(User, User.id == Question.author_user_id)
        .options(joinedload(Question.solutions))
        .where(Question.topic_id == topic_id)
        .order_by(Question.id)
    )
    if not include_hidden:
        stmt = stmt.where(*_public_question_filter())
    if search.strip():
        term = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Question.body.like(term),
                Question.choice_a.like(term),
                Question.choice_b.like(term),
                Question.choice_c.like(term),
                Question.choice_d.like(term),
            )
        )
    if bookmarked_by is not None:
        stmt = stmt.join(
            QuestionFlag,
            (QuestionFlag.question_id == Question.id) & (QuestionFlag.user_id == bookmarked_by.id),
        )
    rows = (await db.execute(stmt.limit(per_page))).scalars().unique().all()
    return [await question_view(db, q, viewer, include_hidden=include_hidden) for q in rows]


async def get_question(db: AsyncSession, question_id: int) -> Question:
    question = await db.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return question


async def create_question(db: AsyncSession, author: User, data: dict) -> Question:
    permissions.require(author.permissions, permissions.POST_QUESTION)
    topic = await db.get(Topic, int(data["topic_id"]))
    if topic is None or not topic.is_active:
        raise HTTPException(status_code=400, detail="Choose an active topic")
    correct = str(data.get("correct_choice", "")).strip().upper()
    if correct not in LETTERS:
        raise HTTPException(status_code=422, detail="Correct choice must be A to E")
    question = Question(
        topic_id=topic.id,
        author_user_id=author.id,
        body=str(data["body"]).strip(),
        choice_a=str(data["choice_a"]).strip(),
        choice_b=str(data["choice_b"]).strip(),
        choice_c=str(data["choice_c"]).strip(),
        choice_d=str(data["choice_d"]).strip(),
        choice_e=(str(data["choice_e"]).strip() or None) if data.get("choice_e") else None,
        correct_choice=correct,
        explanation=(str(data["explanation"]).strip() or None) if data.get("explanation") else None,
    )
    if not question.body:
        raise HTTPException(status_code=422, detail="The question text is required")
    db.add(question)
    await db.commit()
    await db.refresh(question)
    return question


async def update_question(
    db: AsyncSession, question: Question, actor: User, data: dict
) -> Question:
    owns = question.author_user_id == actor.id
    if not owns and not permissions.has(actor.permissions, permissions.MODERATE):
        raise HTTPException(status_code=403, detail="Not your question")
    correct = str(data.get("correct_choice", question.correct_choice)).strip().upper()
    if correct not in LETTERS:
        raise HTTPException(status_code=422, detail="Correct choice must be A to E")
    question.body = str(data.get("body", question.body)).strip()
    for letter in LETTERS[:4]:
        key = f"choice_{letter.lower()}"
        if key in data:
            setattr(question, key, str(data[key]).strip())
    if "choice_e" in data:
        value = str(data["choice_e"] or "").strip()
        question.choice_e = value or None
    if "explanation" in data:
        value = str(data["explanation"] or "").strip()
        question.explanation = value or None
    question.correct_choice = correct
    await db.commit()
    await db.refresh(question)
    return question


async def hide_question(
    db: AsyncSession, question: Question, actor: User, hidden: bool
) -> Question:
    permissions.require(actor.permissions, permissions.MODERATE)
    question.is_hidden = hidden
    question.hidden_by_user_id = actor.id if hidden else None
    question.hidden_at = None
    if hidden:
        import datetime as dt

        question.hidden_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    await db.commit()
    await db.refresh(question)
    return question


async def record_attempt(db: AsyncSession, question: Question, user: User, chosen: str) -> dict:
    letter = chosen.strip().upper()
    if letter not in LETTERS:
        raise HTTPException(status_code=422, detail="Choose A to E")
    is_correct = letter == question.correct_choice
    existing = (
        (
            await db.execute(
                select(QuestionAttempt).where(
                    QuestionAttempt.question_id == question.id,
                    QuestionAttempt.user_id == user.id,
                )
            )
        )
        .scalars()
        .first()
    )
    if existing is None:
        db.add(
            QuestionAttempt(
                question_id=question.id,
                user_id=user.id,
                chosen=letter,
                is_correct=is_correct,
            )
        )
    else:
        existing.chosen = letter
        existing.is_correct = is_correct
    await db.commit()
    return {"chosen": letter, "is_correct": is_correct, "correct_choice": question.correct_choice}


async def toggle_bookmark(db: AsyncSession, question: Question, user: User) -> bool:
    existing = (
        (
            await db.execute(
                select(QuestionFlag).where(
                    QuestionFlag.question_id == question.id, QuestionFlag.user_id == user.id
                )
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        await db.delete(existing)
        await db.commit()
        return False
    db.add(QuestionFlag(question_id=question.id, user_id=user.id))
    await db.commit()
    return True


async def progress_for(db: AsyncSession, user: User) -> dict:
    rows = await db.execute(
        select(
            func.count(QuestionAttempt.id),
            func.sum(func.coalesce(QuestionAttempt.is_correct, 0)),
        ).where(QuestionAttempt.user_id == user.id)
    )
    answered_raw, correct_raw = rows.one()
    answered = int(answered_raw or 0)
    correct_count = int(correct_raw or 0)
    return {
        "answered": answered,
        "correct": correct_count,
        "accuracy": round(correct_count / answered * 100) if answered else 0,
        "bookmarks": int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(QuestionFlag)
                    .where(QuestionFlag.user_id == user.id)
                )
            ).scalar_one()
        ),
    }


async def hidden_content(db: AsyncSession) -> dict:
    """Everything the public site is not showing, for the administrator."""
    hidden_questions = (
        await db.execute(
            select(Question, User.username, Topic.name, Subject.name)
            .join(User, User.id == Question.author_user_id)
            .join(Topic, Topic.id == Question.topic_id)
            .join(Subject, Subject.id == Topic.subject_id)
            .where(Question.is_hidden.is_(True))
            .order_by(Question.id.desc())
        )
    ).all()
    hidden_solutions = (
        await db.execute(
            select(Solution, User.username, Question.body)
            .join(User, User.id == Solution.author_user_id)
            .join(Question, Question.id == Solution.question_id)
            .where(Solution.is_hidden.is_(True))
            .order_by(Solution.id.desc())
        )
    ).all()
    return {
        "questions": [
            {
                "id": q.id,
                "body": q.body,
                "topic": topic,
                "subject": subject,
                "author": username,
                "hidden_at": q.hidden_at,
            }
            for q, username, topic, subject in hidden_questions
        ],
        "solutions": [
            {
                "id": s.id,
                "question_id": s.question_id,
                "question": body[:160],
                "author": username,
                "hidden_at": s.hidden_at,
            }
            for s, username, body in hidden_solutions
        ],
    }
