"""Quiz mode: build a paper, run it, and score it.

A quiz is not stored. The whole thing, question ids and settings, is packed into a
code the member can keep or hand to somebody else, and the code is the only state:
two people with the same code answer the same questions in the same order. That is
what makes it usable for a contest without a lobby, a room, or a database row.

Answers are recorded as ordinary attempts, so a quiz counts toward the same
numbers the profile shows. The rules are the ones the question page uses: the
first selection is kept, a correct answer locks the sheet, and further tries cost
an attempt.
"""

from __future__ import annotations

import base64
import json
import random
import zlib

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Question, QuestionAttempt, QuestionFlag, Tag, User, question_tags
from app.services import metrics

# The bank a topic offers to a quiz: the best-considered questions first.
POOL_PER_TOPIC = 1000
MAX_QUESTIONS = 300
COMPUTATION_TAG = "computation"
CODE_VERSION = 1


def _score_subquery():
    return (
        select(
            QuestionFlag.question_id.label("question_id"),
            func.coalesce(func.sum(QuestionFlag.vote), 0).label("score"),
        )
        .group_by(QuestionFlag.question_id)
        .subquery()
    )


def _filters(query, filters: dict, viewer: User | None):
    """Apply the shared filter set used by the builder and by random mode."""
    if filters.get("exclude_computation"):
        tagged = (
            select(question_tags.c.question_id)
            .join(Tag, Tag.id == question_tags.c.tag_id)
            .where(Tag.name == COMPUTATION_TAG)
        )
        query = query.where(Question.id.not_in(tagged))
    if viewer is not None:
        if filters.get("unanswered_only"):
            answered = select(QuestionAttempt.question_id).where(
                QuestionAttempt.user_id == viewer.id
            )
            query = query.where(Question.id.not_in(answered))
        if filters.get("favourites_only"):
            starred = select(QuestionFlag.question_id).where(
                QuestionFlag.user_id == viewer.id,
                QuestionFlag.is_favourite.is_(True),
            )
            query = query.where(Question.id.in_(starred))
    return query


async def topic_pool(
    db: AsyncSession, topic_id: int, filters: dict, viewer: User | None
) -> tuple[int, list[int]]:
    """How many questions this topic offers, and the ids a quiz may draw from."""
    scores = _score_subquery()
    base = (
        select(Question.id)
        .join(User, User.id == Question.author_user_id)
        .where(
            Question.topic_id == topic_id,
            Question.is_hidden.is_(False),
            Question.is_deleted.is_(False),
            User.status == "active",
        )
        .outerjoin(scores, scores.c.question_id == Question.id)
    )
    base = _filters(base, filters, viewer)
    total = int((await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one())
    ranked = base.order_by(func.coalesce(scores.c.score, 0).desc(), Question.id.desc()).limit(
        POOL_PER_TOPIC
    )
    ids = list((await db.execute(ranked)).scalars().all())
    return total, ids


async def bank_sizes(db: AsyncSession) -> dict[int, int]:
    """Question counts per topic, for the builder. One query, not one per topic."""
    rows = (
        await db.execute(
            select(Question.topic_id, func.count())
            .join(User, User.id == Question.author_user_id)
            .where(
                Question.is_hidden.is_(False),
                Question.is_deleted.is_(False),
                User.status == "active",
            )
            .group_by(Question.topic_id)
        )
    ).all()
    return {int(topic_id): int(total) for topic_id, total in rows}


async def build(
    db: AsyncSession,
    selections: dict[int, int],
    settings: dict,
    viewer: User,
) -> tuple[dict, list[int]]:
    """Choose the questions and put them in the order the settings ask for."""
    filters = settings.get("filters") or {}
    wanted = {int(topic): int(count) for topic, count in selections.items() if int(count) > 0}
    if not wanted:
        raise HTTPException(status_code=422, detail="Choose at least one question")
    if sum(wanted.values()) > MAX_QUESTIONS:
        raise HTTPException(
            status_code=422, detail=f"A quiz holds at most {MAX_QUESTIONS} questions"
        )

    picked: list[tuple[int, list[int]]] = []
    for topic_id, count in wanted.items():
        _total, pool = await topic_pool(db, topic_id, filters, viewer)
        if not pool:
            continue
        take = min(count, len(pool))
        picked.append((topic_id, random.sample(pool, take)))

    if not picked:
        raise HTTPException(status_code=422, detail="Nothing in the bank matches those filters")

    group = settings.get("group", "mixed")
    ordered: list[int] = []
    if group == "topic":
        blocks = [(topic_id, random.sample(ids, len(ids))) for topic_id, ids in picked]
        random.shuffle(blocks)
        for _topic_id, ids in blocks:
            ordered.extend(ids)
    elif group == "subject":
        subjects = await _topics_to_subjects(db, [topic_id for topic_id, _ in picked])
        grouped: dict[int, list[int]] = {}
        for topic_id, ids in picked:
            grouped.setdefault(subjects.get(topic_id, 0), []).extend(ids)
        for subject_id in random.sample(list(grouped), len(grouped)):
            block = grouped[subject_id]
            random.shuffle(block)
            ordered.extend(block)
    else:
        for _topic_id, ids in picked:
            ordered.extend(ids)
        random.shuffle(ordered)

    return settings, ordered


async def _topics_to_subjects(db: AsyncSession, topic_ids: list[int]) -> dict[int, int]:
    from app.models import Topic

    rows = (
        await db.execute(select(Topic.id, Topic.subject_id).where(Topic.id.in_(topic_ids)))
    ).all()
    return {topic_id: subject_id for topic_id, subject_id in rows}


def encode(settings: dict, ids: list[int]) -> str:
    """Pack a quiz into a code: settings and question order, nothing else."""
    payload = {"v": CODE_VERSION, "s": settings, "q": ids}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode().rstrip("=")


def decode(code: str) -> tuple[dict, list[int]]:
    padded = code + "=" * (-len(code) % 4)
    try:
        payload = json.loads(zlib.decompress(base64.urlsafe_b64decode(padded)))
    except Exception as exc:
        raise HTTPException(status_code=422, detail="That quiz code is not readable") from exc
    if payload.get("v") != CODE_VERSION or not isinstance(payload.get("q"), list):
        raise HTTPException(status_code=422, detail="That quiz code is not readable")
    ids = [int(value) for value in payload["q"]][:MAX_QUESTIONS]
    if not ids:
        raise HTTPException(status_code=422, detail="That quiz code has no questions")
    return payload.get("s") or {}, ids


async def questions_for(db: AsyncSession, ids: list[int]) -> list[Question]:
    """The questions a code names, in the code's order, minus anything gone."""
    rows = (await db.execute(select(Question).where(Question.id.in_(ids)))).scalars().all()
    by_id = {question.id: question for question in rows}
    return [by_id[question_id] for question_id in ids if question_id in by_id]


async def random_question(db: AsyncSession, filters: dict, viewer: User) -> dict:
    """One question, unplanned, from whatever the filters leave."""
    scores = _score_subquery()
    query = (
        select(Question.id, Question.topic_id)
        .join(User, User.id == Question.author_user_id)
        .where(
            Question.is_hidden.is_(False),
            Question.is_deleted.is_(False),
            User.status == "active",
        )
        .outerjoin(scores, scores.c.question_id == Question.id)
    )
    excluded = [int(topic) for topic in filters.get("exclude_topics") or []]
    if excluded:
        query = query.where(Question.topic_id.not_in(excluded))
    if filters.get("subject_id"):
        from app.models import Topic

        query = query.where(
            Question.topic_id.in_(
                select(Topic.id).where(Topic.subject_id == int(filters["subject_id"]))
            )
        )
    query = _filters(query, filters, viewer)
    # `random()` is SQLite and `RAND()` is MySQL, so the choice is made here from a
    # capped sample instead of asking either dialect to do it.
    rows = (await db.execute(query.limit(2000))).all()
    if not rows:
        raise HTTPException(status_code=404, detail="Nothing matches those filters")
    question_id, topic_id = random.choice(rows)
    return {"question_id": int(question_id), "topic_id": int(topic_id)}


async def submit(db: AsyncSession, user: User, answers: dict[int, str]) -> dict:
    """Score a finished quiz and record every answer as an attempt."""
    if not answers:
        raise HTTPException(status_code=422, detail="No answers to submit")
    if len(answers) > MAX_QUESTIONS:
        raise HTTPException(status_code=422, detail="That is more answers than a quiz holds")

    question_ids = [int(value) for value in answers]
    rows = (await db.execute(select(Question).where(Question.id.in_(question_ids)))).scalars().all()
    by_id = {question.id: question for question in rows}

    existing = {
        attempt.question_id: attempt
        for attempt in (
            await db.execute(
                select(QuestionAttempt).where(
                    QuestionAttempt.user_id == user.id,
                    QuestionAttempt.question_id.in_(question_ids),
                )
            )
        )
        .scalars()
        .all()
    }

    results = []
    for question_id in question_ids:
        question = by_id.get(question_id)
        if question is None or question.is_deleted:
            continue
        letter = str(answers[question_id]).strip().upper()[:1]
        if letter not in {"A", "B", "C", "D", "E"}:
            continue
        row = existing.get(question.id)
        if row is not None and row.is_correct:
            # Already solved: the quiz does not get a second bite, and the sheet
            # is not inflated by a paper answered twice.
            results.append(_result(question, letter, "already solved", row.attempts))
            continue
        correct = letter == question.correct_choice
        if row is None:
            db.add(
                QuestionAttempt(
                    question_id=question.id,
                    user_id=user.id,
                    chosen=letter,
                    first_selection=letter,
                    first_correct=correct,
                    is_correct=correct,
                    attempts=1,
                )
            )
            results.append(_result(question, letter, correct, 1))
        else:
            row.chosen = letter
            row.is_correct = row.is_correct or correct
            row.attempts = max(int(row.attempts or 0), 1) + 1
            results.append(_result(question, letter, correct, row.attempts))

    await db.flush()
    await metrics.refresh_user(db, user.id)
    await db.commit()

    scored = [item for item in results if item["status"] != "already solved"]
    return {
        "results": results,
        "total": len(results),
        "correct": sum(1 for item in results if item["correct"]),
        "scored": len(scored),
        "score": round(100 * sum(1 for item in scored if item["correct"]) / len(scored))
        if scored
        else 0,
    }


def _result(question: Question, chosen: str, status, attempts: int) -> dict:
    correct = status is True or (status == "already solved")
    return {
        "question_id": question.id,
        "topic_id": question.topic_id,
        "chosen": chosen,
        "correct_choice": question.correct_choice,
        "correct": bool(correct),
        "status": status if isinstance(status, str) else ("correct" if status else "wrong"),
        "attempts": attempts,
        "body": question.body[:160],
    }
