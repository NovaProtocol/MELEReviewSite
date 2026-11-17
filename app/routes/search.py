"""Search and tags.

The member search is not live: it runs when submitted, because a live one would
hit the database on every keystroke for every reader. The admin search is live,
because there are a handful of administrators and finding a question quickly is
the whole job.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import permissions
from app.auth import check_csrf, require_user
from app.db import get_db
from app.models import Question, Subject, Topic, User
from app.services import taxonomy

router = APIRouter(prefix="/api", tags=["search"])


def _split_tags(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


async def results_for(
    db: AsyncSession, questions: list[Question], *, with_stats: bool
) -> list[dict]:
    """Shape questions for a search result list: taxonomy names, tags, stats."""
    ids = [question.id for question in questions]
    tags = await taxonomy.tags_for_questions(db, ids)
    stats = await taxonomy.stats_for_questions(db, ids) if with_stats else {}

    names: dict[int, tuple[str, str]] = {}
    if ids:
        rows = await db.execute(
            select(Topic.id, Topic.name, Subject.name)
            .join(Subject, Subject.id == Topic.subject_id)
            .where(Topic.id.in_({question.topic_id for question in questions}))
        )
        names = {topic_id: (topic, subject) for topic_id, topic, subject in rows.all()}

    out = []
    for question in questions:
        topic_name, subject_name = names.get(question.topic_id, (None, None))
        item = {
            "id": question.id,
            "topic_id": question.topic_id,
            "body": question.body,
            "author_user_id": question.author_user_id,
            "is_hidden": question.is_hidden,
            "is_deleted": question.is_deleted,
            "tags": tags.get(question.id, []),
            "topic": topic_name,
            "subject": subject_name,
            "date_created": question.date_created,
        }
        if with_stats:
            item.update(stats.get(question.id, {}))
        out.append(item)
    return out


@router.get("/search")
async def search(
    q: str = "",
    tags: str = "",
    subject: int | None = None,
    topic: int | None = None,
    limit: int = 100,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Member search. Submitted, not live, and it never returns a correct answer."""
    selected = _split_tags(tags)
    questions = await taxonomy.search_questions(
        db,
        term=q,
        tags=selected,
        subject_id=subject,
        topic_id=topic,
        limit=limit,
    )
    return {
        "query": q,
        "tags": selected,
        "results": await results_for(db, questions, with_stats=False),
        "suggested_tags": await taxonomy.tag_suggestions(db, q) if q.strip() else [],
    }


@router.get("/tags")
async def list_tags(
    counts: bool = False,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return await taxonomy.list_tags(db, with_counts=counts)


@router.get("/tags/{name}/questions")
async def questions_with_tag(
    name: str,
    limit: int = 100,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Every question carrying one tag.

    The tag index only ever returned tag names and counts, so a tag page had
    nothing to list. This is the list, and it goes through the same search the
    member page uses so a tag cannot answer what search would not.
    """
    from app.services import library as library_service

    found = await taxonomy.search_questions(db, tags=[taxonomy.normalise_tag(name)], limit=limit)
    out = []
    for question in found:
        out.append(await library_service.question_view(db, question, user, with_solutions=False))
    return out


@router.post("/tags")
async def create_tag(
    request: Request,
    body: dict,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a tag on its own, so a tag can exist before a question carries it."""
    check_csrf(request)
    permissions.require(user.permissions, permissions.POST_QUESTION)
    name = taxonomy.normalise_tag(str(body.get("name", "")))
    tag = await taxonomy.get_or_create(db, name)
    await db.commit()
    return {"id": tag.id, "name": tag.name}
