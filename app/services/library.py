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


async def _scores(db: AsyncSession, question_ids: list[int]) -> dict[int, int]:
    """Community score per question: the sum of every member's vote."""
    if not question_ids:
        return {}
    rows = await db.execute(
        select(QuestionFlag.question_id, func.coalesce(func.sum(QuestionFlag.vote), 0))
        .where(QuestionFlag.question_id.in_(question_ids))
        .group_by(QuestionFlag.question_id)
    )
    return {qid: int(score or 0) for qid, score in rows.all()}


async def _personal(db: AsyncSession, question_ids: list[int], viewer: User | None) -> dict:
    """This member's flags, so a list renders without a query per card."""
    if viewer is None or not question_ids:
        return {}
    rows = await db.execute(
        select(QuestionFlag).where(
            QuestionFlag.question_id.in_(question_ids), QuestionFlag.user_id == viewer.id
        )
    )
    return {flag.question_id: flag for flag in rows.scalars().all()}


async def question_view(
    db: AsyncSession,
    question: Question,
    viewer: User | None = None,
    *,
    include_hidden: bool = False,
    with_solutions: bool = True,
    score: int | None = None,
    flag: QuestionFlag | None = None,
) -> dict:
    author = await db.get(User, question.author_user_id)
    solutions = []
    if with_solutions:
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
    if with_solutions:
        solution_count = len(solutions)
    else:
        solution_count = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Solution)
                    .join(User, User.id == Solution.author_user_id)
                    .where(
                        Solution.question_id == question.id,
                        *([] if include_hidden else _public_solution_filter()),
                    )
                )
            ).scalar_one()
        )
    attempt = None
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
    if score is None:
        score = (await _scores(db, [question.id])).get(question.id, 0)
    return {
        "id": question.id,
        "topic_id": question.topic_id,
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
        "author_avatar": f"/media/{author.avatar_path}" if author and author.avatar_path else None,
        "author_status": author.status if author else None,
        "solutions": solutions,
        "solution_count": solution_count,
        "attempt": attempt,
        "score": score,
        "vote": flag.vote if flag else 0,
        "is_favourite": bool(flag.is_favourite) if flag else False,
        "is_hidden_by_me": bool(flag.is_hidden) if flag else False,
        "date_created": question.date_created,
    }


async def list_questions(
    db: AsyncSession,
    topic_id: int,
    search: str = "",
    include_moderated_hidden: bool = False,
    include_personal_hidden: bool = False,
    viewer: User | None = None,
    favourites_only: bool = False,
    show_downvoted: bool = False,
    per_page: int = 200,
) -> list[dict]:
    """The visible list for one topic.

    Two kinds of hidden, kept apart on purpose:

    - ``include_moderated_hidden`` is a moderator's view of what a moderator hid.
      It is separate so that a moderator's own eye button still works on their own
      list; holding VIEW_HIDDEN must not make the eye appear broken.
    - ``include_personal_hidden`` is the viewer's own "Show hidden" toggle.

    Plus ``show_downvoted`` for community-hidden questions and ``favourites_only``,
    which overrides the personal hide: a starred question you hid is still starred,
    and asking for your favourites is an explicit request to see them.
    """
    stmt = (
        select(Question)
        .join(User, User.id == Question.author_user_id)
        .options(joinedload(Question.solutions))
        .where(Question.topic_id == topic_id)
        .order_by(Question.id)
    )
    if not include_moderated_hidden:
        stmt = stmt.where(Question.is_hidden.is_(False), User.status == "active")
    else:
        stmt = stmt.where(User.status == "active")
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

    personal = (
        select(QuestionFlag.question_id)
        .where(QuestionFlag.user_id == viewer.id if viewer else False)
        .subquery()
    )
    scores = (
        select(
            QuestionFlag.question_id.label("question_id"),
            func.sum(QuestionFlag.vote).label("score"),
        )
        .group_by(QuestionFlag.question_id)
        .subquery()
    )

    if viewer is not None:
        stmt = stmt.outerjoin(
            QuestionFlag,
            (QuestionFlag.question_id == Question.id) & (QuestionFlag.user_id == viewer.id),
        )
        if favourites_only:
            stmt = stmt.where(QuestionFlag.is_favourite.is_(True))
        elif not include_personal_hidden:
            stmt = stmt.where(
                or_(QuestionFlag.is_hidden.is_(None), QuestionFlag.is_hidden.is_(False))
            )
        _ = personal

    stmt = stmt.outerjoin(scores, scores.c.question_id == Question.id)
    negative = func.coalesce(scores.c.score, 0) < 0
    if not show_downvoted:
        stmt = stmt.where(~negative)

    rows = (await db.execute(stmt.limit(per_page))).scalars().unique().all()
    ids = [q.id for q in rows]
    score_map = await _scores(db, ids)
    flag_map = await _personal(db, ids, viewer)
    return [
        await question_view(
            db,
            q,
            viewer,
            include_hidden=include_moderated_hidden,
            with_solutions=False,
            score=score_map.get(q.id, 0),
            flag=flag_map.get(q.id),
        )
        for q in rows
    ]


async def set_favourite(db: AsyncSession, question: Question, user: User) -> dict:
    flag = await _flag_row(db, question.id, user.id)
    flag.is_favourite = not flag.is_favourite
    await db.commit()
    return await _flag_state(db, question.id, flag)


async def set_personal_hidden(db: AsyncSession, question: Question, user: User) -> dict:
    """Hide a question for this member only. Favourite and hide are independent."""
    flag = await _flag_row(db, question.id, user.id)
    flag.is_hidden = not flag.is_hidden
    await db.commit()
    return await _flag_state(db, question.id, flag)


async def set_vote(db: AsyncSession, question: Question, user: User, direction: int) -> dict:
    """Apply an up or down vote; voting the same way twice clears the vote."""
    if direction not in (-1, 0, 1):
        raise HTTPException(status_code=422, detail="Vote must be -1, 0 or 1")
    flag = await _flag_row(db, question.id, user.id)
    flag.vote = 0 if flag.vote == direction else direction
    await db.commit()
    return await _flag_state(db, question.id, flag)


async def _flag_row(db: AsyncSession, question_id: int, user_id: int) -> QuestionFlag:
    row = (
        (
            await db.execute(
                select(QuestionFlag).where(
                    QuestionFlag.question_id == question_id, QuestionFlag.user_id == user_id
                )
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        row = QuestionFlag(question_id=question_id, user_id=user_id)
        db.add(row)
        await db.flush()
    return row


async def _flag_state(db: AsyncSession, question_id: int, flag: QuestionFlag) -> dict:
    score = (await _scores(db, [question_id])).get(question_id, 0)
    return {
        "question_id": question_id,
        "vote": flag.vote,
        "score": score,
        "is_favourite": bool(flag.is_favourite),
        "is_hidden_by_me": bool(flag.is_hidden),
    }


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
        "favourites": int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(QuestionFlag)
                    .where(QuestionFlag.user_id == user.id, QuestionFlag.is_favourite.is_(True))
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
