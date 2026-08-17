from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import Account, Question, Tag, question_flags, question_tags
from api.schemas import QuestionWrite


async def _tag_ids(db: AsyncSession, names: list[str]) -> list[int]:
    ids = []
    for raw in names:
        name = raw.strip()
        if not name:
            continue
        result = await db.execute(select(Tag).where(Tag.name == name))
        tag = result.scalar_one_or_none()
        if tag is None:
            tag = Tag(name=name)
            db.add(tag)
            await db.flush()
        ids.append(tag.id)
    return ids


async def _set_tags(db: AsyncSession, question_id: int, names: list[str]) -> None:
    await db.execute(delete(question_tags).where(question_tags.c.question_id == question_id))
    for tag_id in await _tag_ids(db, names):
        await db.execute(insert(question_tags).values(question_id=question_id, tag_id=tag_id))


async def tags_for_questions(db: AsyncSession, ids: list[int]) -> dict[int, list[str]]:
    """Bulk fetch tag names per question id (avoids async lazy-loading)."""
    if not ids:
        return {}
    result = await db.execute(
        select(question_tags.c.question_id, Tag.name)
        .join(Tag, Tag.id == question_tags.c.tag_id)
        .where(question_tags.c.question_id.in_(ids))
        .order_by(Tag.name)
    )
    out: dict[int, list[str]] = {qid: [] for qid in ids}
    for qid, name in result.all():
        out.setdefault(qid, []).append(name)
    return out


def _apply(question: Question, data: QuestionWrite) -> None:
    question.question_text = data.question_text
    question.choice_a = data.choice_a
    question.choice_b = data.choice_b
    question.choice_c = data.choice_c
    question.choice_d = data.choice_d
    question.choice_e = data.choice_e
    question.answer = data.answer
    question.solution = data.solution
    question.active = data.active


async def create_question(db: AsyncSession, data: QuestionWrite, account_id: int | None = None) -> Question:
    question = Question(
        question_text=data.question_text,
        choice_a=data.choice_a,
        choice_b=data.choice_b,
        choice_c=data.choice_c,
        choice_d=data.choice_d,
        choice_e=data.choice_e,
        answer=data.answer,
        solution=data.solution,
        active=data.active,
        account_id=account_id,
    )
    db.add(question)
    await db.flush()
    await _set_tags(db, question.id, data.tags)
    await db.commit()
    return question


async def get_question(db: AsyncSession, question_id: int) -> Question:
    question = await db.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    return question


async def update_question(db: AsyncSession, question_id: int, data: QuestionWrite) -> Question:
    question = await get_question(db, question_id)
    _apply(question, data)
    await _set_tags(db, question_id, data.tags)
    await db.commit()
    return question


async def delete_question(db: AsyncSession, question_id: int) -> None:
    question = await get_question(db, question_id)
    await db.delete(question)  # solutions cascade
    await db.commit()


async def toggle_flag(db: AsyncSession, question_id: int, account_id: int) -> Question:
    question = await get_question(db, question_id)

    existing = (
        await db.execute(
            select(question_flags).where(
                question_flags.c.question_id == question_id,
                question_flags.c.account_id == account_id,
            )
        )
    ).scalar_one_or_none()

    if existing:
        await db.execute(
            delete(question_flags).where(
                question_flags.c.question_id == question_id,
                question_flags.c.account_id == account_id,
            )
        )
    else:
        await db.execute(
            insert(question_flags).values(question_id=question_id, account_id=account_id)
        )

    flag_count = (
        await db.execute(
            select(func.count()).select_from(question_flags).where(
                question_flags.c.question_id == question_id
            )
        )
    ).scalar_one()

    total = (
        await db.execute(
            select(func.count(Account.id)).where(Account.disabled.is_(False))
        )
    ).scalar_one()

    threshold = max(1, total // 10)
    question.flagged = flag_count > 0
    if flag_count >= threshold:
        question.active = False

    await db.commit()
    return question


async def set_answer(db: AsyncSession, question_id: int, answer: int | None) -> Question:
    question = await get_question(db, question_id)
    question.answer = answer
    await db.commit()
    return question


async def list_questions(
    db: AsyncSession,
    search: str = "",
    tag: str = "",
    include_inactive: bool = False,
    page: int = 1,
    per_page: int = 100,
) -> tuple[list[Question], int]:
    """Return (questions, total). By default only active questions are shown."""
    conditions = []
    if not include_inactive:
        conditions.append(Question.active.is_(True))

    if search:
        term = search.strip()
        conditions.append(or_(
            func.instr(Question.question_text, term) > 0,
            func.instr(Question.choice_a, term) > 0,
            func.instr(Question.choice_b, term) > 0,
            func.instr(Question.choice_c, term) > 0,
            func.instr(Question.choice_d, term) > 0,
        ))

    query = select(Question)
    if tag:
        tag_trim = tag.strip()
        query = query.join(question_tags, question_tags.c.question_id == Question.id)
        query = query.join(Tag, Tag.id == question_tags.c.tag_id)
        conditions.append(Tag.name == tag_trim)

    count_stmt = select(func.count(func.distinct(Question.id)))
    if conditions:
        count_stmt = count_stmt.where(*conditions)

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = query.where(*conditions).order_by(Question.id).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def list_tags(db: AsyncSession) -> list[Tag]:
    result = await db.execute(select(Tag).order_by(Tag.name))
    return list(result.scalars().all())


def question_dict(q: Question, tags: list[str], author_name: str | None = None) -> dict:
    return {
        "id": q.id,
        "question_text": q.question_text,
        "choice_a": q.choice_a,
        "choice_b": q.choice_b,
        "choice_c": q.choice_c,
        "choice_d": q.choice_d,
        "choice_e": q.choice_e,
        "answer": q.answer,
        "solution": q.solution,
        "flagged": q.flagged,
        "active": q.active,
        "account_id": q.account_id,
        "author_name": author_name,
        "tags": tags,
        "date_created": q.date_created,
    }


def check_ownership(question: Question, account) -> None:
    if question.account_id is None and account.is_admin:
        return
    if question.account_id == account.id:
        return
    raise HTTPException(status_code=403, detail="Not your question")
