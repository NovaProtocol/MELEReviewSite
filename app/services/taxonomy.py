"""Tags, the cross-cutting labels, and question search.

Tags exist because the taxonomy is a tree and study is not. A derivative question
lives under exactly one topic, but the idea of a derivative also shows up in
kinematics, in economics and in thermodynamics. A tag is the only thing that can
gather those together.

Search is deliberately not one query. There are three different questions:

- ``search_questions`` — a text match across the statement and choices, with
  optional tag and taxonomy filters. Used by the member search page and the admin
  list, which differ only in whether deleted and hidden rows are included.
- ``tag_suggestions`` — which tags look like the words that were typed, so a
  search for "rankine" can point at the `rankine` tag instead of only matching
  question bodies.
- ``facet_counts`` — how many questions each tag has, for the browse list.

Names are normalised on write (lowercase, spaces and punctuation collapsed to a
hyphen) so `Differential Equation`, `differential equation` and
`differential-equation` are one tag and not three.
"""

from __future__ import annotations

import re

from fastapi import HTTPException
from sqlalchemy import Integer, case, cast, delete, func, insert, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Question,
    QuestionAttempt,
    QuestionFlag,
    Tag,
    Topic,
    User,
    question_tags,
)

TAG_NAME_MAX = 40
_TAG_CLEAN = re.compile(r"[^a-z0-9]+")


def normalise_tag(raw: str) -> str:
    """`Differential Equation` -> `differential-equation`, and validate it."""
    cleaned = _TAG_CLEAN.sub("-", raw.strip().lower()).strip("-")
    if not cleaned:
        raise HTTPException(status_code=422, detail="A tag needs at least one letter or digit")
    if len(cleaned) > TAG_NAME_MAX:
        raise HTTPException(
            status_code=422, detail=f"A tag may be at most {TAG_NAME_MAX} characters"
        )
    return cleaned


async def get_or_create(db: AsyncSession, raw: str) -> Tag:
    name = normalise_tag(raw)
    existing = (await db.execute(select(Tag).where(Tag.name == name))).scalars().first()
    if existing is not None:
        return existing
    tag = Tag(name=name)
    db.add(tag)
    await db.flush()
    return tag


async def set_question_tags(db: AsyncSession, question_id: int, names: list[str]) -> None:
    """Replace a question's tags with the given names, creating any that are new."""
    await db.execute(delete(question_tags).where(question_tags.c.question_id == question_id))
    seen: set[str] = set()
    for raw in names:
        name = normalise_tag(raw)
        if name in seen:
            continue
        seen.add(name)
        tag = await get_or_create(db, name)
        await db.execute(insert(question_tags).values(question_id=question_id, tag_id=tag.id))


async def tags_for_questions(db: AsyncSession, question_ids: list[int]) -> dict[int, list[str]]:
    if not question_ids:
        return {}
    rows = await db.execute(
        select(question_tags.c.question_id, Tag.name)
        .join(Tag, Tag.id == question_tags.c.tag_id)
        .where(question_tags.c.question_id.in_(question_ids))
        .order_by(Tag.name)
    )
    out: dict[int, list[str]] = {qid: [] for qid in question_ids}
    for question_id, name in rows.all():
        out.setdefault(question_id, []).append(name)
    return out


async def list_tags(db: AsyncSession, *, with_counts: bool = False) -> list[dict]:
    """All tags, optionally with how many live questions carry each."""
    if not with_counts:
        plain = (await db.execute(select(Tag).order_by(Tag.name))).scalars().all()
        return [{"id": tag.id, "name": tag.name} for tag in plain]
    counted = await db.execute(
        select(Tag.id, Tag.name, func.count(question_tags.c.question_id))
        .outerjoin(
            question_tags,
            question_tags.c.tag_id == Tag.id,
        )
        .outerjoin(
            Question,
            (Question.id == question_tags.c.question_id) & Question.is_deleted.is_(False),
        )
        .group_by(Tag.id, Tag.name)
        .order_by(Tag.name)
    )
    return [
        {"id": tag_id, "name": name, "questions": int(count)}
        for tag_id, name, count in counted.all()
    ]


async def tag_suggestions(db: AsyncSession, term: str, limit: int = 5) -> list[str]:
    """Tags whose name contains the term, for the "did you mean a tag" hint."""
    cleaned = _TAG_CLEAN.sub("-", term.strip().lower()).strip("-")
    if not cleaned:
        return []
    rows = await db.execute(
        select(Tag.name)
        .join(question_tags, question_tags.c.tag_id == Tag.id)
        .group_by(Tag.name)
        .having(func.count(question_tags.c.question_id) > 0)
        .order_by(func.count(question_tags.c.question_id).desc(), Tag.name)
    )
    names = [name for (name,) in rows.all()]
    exact = [name for name in names if name == cleaned]
    partial = [name for name in names if cleaned in name and name != cleaned]
    return (exact + partial)[:limit]


async def search_questions(
    db: AsyncSession,
    *,
    term: str = "",
    tags: list[str] | None = None,
    subject_id: int | None = None,
    topic_id: int | None = None,
    include_hidden: bool = False,
    include_deleted: bool = False,
    only_negative: bool = False,
    only_deleted: bool = False,
    author_id: int | None = None,
    limit: int = 200,
) -> list[Question]:
    """Questions matching the filters, newest first.

    The keyword match covers the statement and every choice, and is a plain
    `LIKE '%term%'`. On SQLite `LIKE` is case-insensitive for ASCII, which matches
    MySQL's default collation, so one expression behaves the same on both.
    """
    stmt = select(Question).join(User, User.id == Question.author_user_id)

    if topic_id is not None:
        stmt = stmt.where(Question.topic_id == topic_id)
    elif subject_id is not None:
        stmt = stmt.join(Topic, Topic.id == Question.topic_id).where(Topic.subject_id == subject_id)
    if author_id is not None:
        stmt = stmt.where(Question.author_user_id == author_id)

    if only_deleted:
        stmt = stmt.where(Question.is_deleted.is_(True))
    elif not include_deleted:
        stmt = stmt.where(Question.is_deleted.is_(False))

    if not include_hidden:
        stmt = stmt.where(Question.is_hidden.is_(False), User.status == "active")

    if term.strip():
        like = f"%{term.strip()}%"
        stmt = stmt.where(
            or_(
                Question.body.like(like),
                Question.choice_a.like(like),
                Question.choice_b.like(like),
                Question.choice_c.like(like),
                Question.choice_d.like(like),
                Question.explanation.like(like),
            )
        )

    if tags:
        wanted = [normalise_tag(raw) for raw in tags]
        matched = (
            select(question_tags.c.question_id)
            .join(Tag, Tag.id == question_tags.c.tag_id)
            .where(Tag.name.in_(wanted))
            .group_by(question_tags.c.question_id)
            # Every requested tag must be present, so two tags narrow rather than widen.
            .having(func.count(func.distinct(Tag.name)) == len(wanted))
        )
        stmt = stmt.where(Question.id.in_(matched))

    if only_negative:
        scores = (
            select(
                QuestionFlag.question_id,
                func.coalesce(func.sum(QuestionFlag.vote), 0).label("score"),
            )
            .group_by(QuestionFlag.question_id)
            .subquery()
        )
        stmt = stmt.join(scores, scores.c.question_id == Question.id).where(scores.c.score < 0)

    stmt = stmt.order_by(Question.id.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars().unique().all())


async def stats_for_questions(db: AsyncSession, question_ids: list[int]) -> dict[int, dict]:
    """Score, attempt count and solve rate per question, in three queries."""
    if not question_ids:
        return {}

    scores = {
        qid: int(score or 0)
        for qid, score in (
            await db.execute(
                select(
                    QuestionFlag.question_id,
                    func.coalesce(func.sum(QuestionFlag.vote), 0),
                )
                .where(QuestionFlag.question_id.in_(question_ids))
                .group_by(QuestionFlag.question_id)
            )
        ).all()
    }
    capped_attempts = case((QuestionAttempt.attempts > 4, 4), else_=QuestionAttempt.attempts)
    attempts = {
        qid: (int(total or 0), int(solved or 0), int(capped or 0))
        for qid, total, solved, capped in (
            await db.execute(
                select(
                    QuestionAttempt.question_id,
                    func.count(QuestionAttempt.id),
                    # Cast: SQLite sums a boolean column to a boolean, so an
                    # uncast sum reports True where a count is expected.
                    func.coalesce(func.sum(cast(QuestionAttempt.is_correct, Integer)), 0),
                    func.coalesce(func.sum(capped_attempts), 0),
                )
                .where(QuestionAttempt.question_id.in_(question_ids))
                .group_by(QuestionAttempt.question_id)
            )
        ).all()
    }
    out: dict[int, dict] = {}
    for question_id in question_ids:
        total, solved, capped = attempts.get(question_id, (0, 0, 0))
        out[question_id] = {
            "score": scores.get(question_id, 0),
            "attempters": total,
            "solved": solved,
            "solve_rate": round(solved / total * 100, 1) if total else 0.0,
            "average_attempts": round(capped / total, 2) if total else 0.0,
        }
    return out


SORTS = {
    "newest": "Newest first",
    "attempts": "Most answered",
    "tries": "Most attempts per question",
    "solve_rate": "Lowest solve rate",
    "score": "Lowest score",
}
