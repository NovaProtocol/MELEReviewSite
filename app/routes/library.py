from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import permissions
from app.auth import check_csrf, require_user
from app.db import get_db
from app.models import Reply, Solution, User
from app.services import library as library_service
from app.services import reports as report_service
from app.services import threads as thread_service
from app.services import topic_pages as topic_page_service

router = APIRouter(prefix="/api", tags=["library"])


class QuestionBody(BaseModel):
    topic_id: int
    body: str = Field(min_length=1)
    choice_a: str = Field(min_length=1)
    choice_b: str = Field(min_length=1)
    choice_c: str = Field(min_length=1)
    choice_d: str = Field(min_length=1)
    choice_e: str | None = None
    correct_choice: str = Field(min_length=1, max_length=1)
    # Validated in the service, which can say what is missing in words.
    kind: str = Field(default="", max_length=16)
    explanation: str | None = None
    tags: list[str] = []


class AttemptBody(BaseModel):
    chosen: str = Field(min_length=1, max_length=1)


class VoteBody(BaseModel):
    direction: int = Field(ge=-1, le=1)


class SolutionBody(BaseModel):
    body: str = Field(min_length=1, max_length=20000)


class StrikeBody(BaseModel):
    letter: str = Field(min_length=1, max_length=1)
    value: int = Field(default=1, ge=0, le=1)


class ReportBody(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class DraftBody(BaseModel):
    body: str = Field(default="", max_length=20000)
    publish: bool = False


class ReplyBody(BaseModel):
    body: str = Field(min_length=1, max_length=thread_service.MAX_REPLY)
    parent_id: int | None = None


@router.get("/subjects")
async def subjects(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return await library_service.list_subjects(db)


class TopicPageBody(BaseModel):
    # A chapter transcribed from a book runs long; this is prose, not a form field.
    body: str = Field(default="", max_length=4_000_000)


@router.get("/topics/{topic_id}/pages")
async def read_topic_pages(
    topic_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Both prose panels of a topic, rendered.

    The write side has existed since the panels were added; without a read side a
    client other than the Jinja page could not show them at all, which is the one
    thing that made this API incomplete.
    """
    await library_service.get_topic(db, topic_id)
    pages = await topic_page_service.bodies(db, topic_id)
    for page in pages.values():
        page["may_edit"] = topic_page_service.may_edit(user)
        page["updated_at"] = page["updated_at"].isoformat() if page["updated_at"] else None
        page["updated_by"] = None
    return pages


@router.put("/topics/{topic_id}/pages/{kind}")
async def save_topic_page(
    topic_id: int,
    kind: str,
    request: Request,
    body: TopicPageBody,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Write a topic's study material or reference sheet. Administrator only."""
    check_csrf(request)
    await library_service.get_topic(db, topic_id)
    row = await topic_page_service.save(db, topic_id, kind, body.body, user)
    return {"kind": row.kind, "saved": True}


@router.get("/topics/{topic_id}/questions")
async def questions(
    topic_id: int,
    search: str = "",
    favourites: bool = False,
    show_hidden: bool = False,
    show_downvoted: bool = False,
    answer_state: str = "all",
    has_solution: bool = False,
    mine: bool = False,
    kind: str = "",
    sort: str = "newest",
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """List a topic's questions.

    `show_hidden` reveals what this member hid themselves. A moderator's view of
    moderator-hidden questions is a separate switch, so their own eye button keeps
    working instead of being silently overridden by VIEW_HIDDEN.
    """
    moderator = permissions.has(user.permissions, permissions.VIEW_HIDDEN)
    return await library_service.list_questions(
        db,
        topic_id,
        search=search,
        include_moderated_hidden=moderator,
        include_personal_hidden=show_hidden,
        viewer=user,
        favourites_only=favourites,
        show_downvoted=show_downvoted,
        answer_state=answer_state if answer_state in {"answered", "unanswered"} else "all",
        has_solution=has_solution,
        mine_only=mine,
        kind=kind if kind in {"computation", "identification"} else "",
        sort=sort,
    )


@router.post("/questions", status_code=201)
async def create_question(
    request: Request,
    body: QuestionBody,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    question = await library_service.create_question(db, user, body.model_dump())
    return await library_service.question_view(db, question, user)


@router.get("/questions/{question_id}")
async def get_question(
    question_id: int,
    topic_id: int | None = None,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    question = await library_service.get_question(db, question_id)
    # A question fetched under a topic it does not belong to is a wrong address,
    # and saying 404 is what stops two URLs showing the same problem.
    if topic_id is not None and question.topic_id != topic_id:
        raise HTTPException(status_code=404, detail="Question not found")
    include_hidden = permissions.has(user.permissions, permissions.VIEW_HIDDEN)
    if question.is_hidden and not include_hidden:
        raise HTTPException(status_code=404, detail="Question not found")
    view = await library_service.question_view(db, question, user, include_hidden=include_hidden)
    # Only the detail view asks this: a list would pay for it on every card.
    view["reported_by_me"] = await report_service.has_open_report(db, question.id, user.id)
    return view


@router.put("/questions/{question_id}")
async def update_question(
    question_id: int,
    request: Request,
    body: QuestionBody,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    question = await library_service.get_question(db, question_id)
    updated = await library_service.update_question(db, question, user, body.model_dump())
    return await library_service.question_view(db, updated, user, include_hidden=True)


@router.post("/questions/{question_id}/attempt")
async def attempt(
    question_id: int,
    request: Request,
    body: AttemptBody,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    question = await library_service.get_question(db, question_id)
    return await library_service.record_attempt(db, question, user, body.chosen)


@router.post("/questions/{question_id}/favourite")
async def favourite(
    question_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    question = await library_service.get_question(db, question_id)
    return await library_service.set_favourite(db, question, user)


@router.post("/questions/{question_id}/hide-for-me")
async def hide_for_me(
    question_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Hide the question from this member's own list, not from anyone else's."""
    check_csrf(request)
    question = await library_service.get_question(db, question_id)
    return await library_service.set_personal_hidden(db, question, user)


@router.post("/questions/{question_id}/vote")
async def vote(
    question_id: int,
    request: Request,
    body: VoteBody,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    question = await library_service.get_question(db, question_id)
    return await library_service.set_vote(db, question, user, body.direction)


@router.post("/questions/{question_id}/strike")
async def strike_choice(
    question_id: int,
    request: Request,
    body: StrikeBody,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a choice out, or take the marking back. A note to yourself, not an answer."""
    check_csrf(request)
    question = await library_service.get_question(db, question_id)
    return await library_service.set_strike(db, question, user, body.letter, bool(body.value))


@router.post("/questions/{question_id}/report", status_code=201)
async def report_question(
    question_id: int,
    request: Request,
    body: ReportBody,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    question = await library_service.get_question(db, question_id)
    row = await report_service.report(db, question, user, body.reason)
    return {"id": row.id, "status": row.status}


@router.get("/questions/{question_id}/draft")
async def read_draft(
    question_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """This member's own working for the question, and whether it is published."""
    from app.services import drafts as draft_service

    question = await library_service.get_question(db, question_id)
    body = await draft_service.read(db, question.id, user.id)
    solution = await library_service.my_solution(db, question.id, user.id)
    return {
        "body": body,
        "published": solution is not None,
        "solution_id": solution.id if solution else None,
        "solution_body": (solution.body or "") if solution else "",
    }


@router.put("/questions/{question_id}/draft")
async def save_draft(
    question_id: int,
    request: Request,
    body: DraftBody,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Save the working, and publish or withdraw it.

    Ticking the box publishes the same text as this member's solution; unticking
    withdraws the solution and keeps the working, because losing somebody's writing
    to a checkbox is never what they meant.
    """
    from app.services import drafts as draft_service

    check_csrf(request)
    question = await library_service.get_question(db, question_id)
    await draft_service.save(db, question.id, user.id, body.body)

    if body.publish and body.body.strip():
        # Publishing is a claim that the working answers the question, so it is
        # earned: the same rule that unlocks reading other people's solutions. A
        # disabled switch in the client is a courtesy, not the rule.
        if not await library_service.has_solved(db, question.id, user.id):
            raise HTTPException(
                status_code=403,
                detail="Answer the question correctly before publishing a solution",
            )
        await library_service.save_solution(db, question, user, body.body)
    elif not body.publish:
        existing = await library_service.my_solution(db, question.id, user.id)
        if existing is not None:
            await library_service.remove_solution(db, existing, user)

    refreshed = await library_service.get_question(db, question_id)
    return await library_service.question_view(db, refreshed, user)


@router.post("/questions/{question_id}/solution")
async def save_solution(
    question_id: int,
    request: Request,
    body: SolutionBody,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    question = await library_service.get_question(db, question_id)
    await library_service.save_solution(db, question, user, body.body)
    refreshed = await library_service.get_question(db, question_id)
    return await library_service.question_view(db, refreshed, user)


@router.put("/solutions/{solution_id}")
async def edit_solution(
    solution_id: int,
    request: Request,
    body: SolutionBody,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    solution = await db.get(Solution, solution_id)
    if solution is None:
        raise HTTPException(status_code=404, detail="No such solution")
    await library_service.edit_solution(db, solution, user, body.body)
    refreshed = await library_service.get_question(db, solution.question_id)
    return await library_service.question_view(db, refreshed, user)


@router.delete("/solutions/{solution_id}", status_code=204)
async def remove_solution(
    solution_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    solution = await db.get(Solution, solution_id)
    if solution is None:
        raise HTTPException(status_code=404, detail="No such solution")
    await library_service.remove_solution(db, solution, user)
    return Response(status_code=204)


@router.post("/questions/{question_id}/hide")
async def hide_question(
    question_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    question = await library_service.get_question(db, question_id)
    updated = await library_service.hide_question(db, question, user, True)
    return {"id": updated.id, "is_hidden": updated.is_hidden}


@router.post("/solutions/{solution_id}/hide")
async def hide_solution(
    solution_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    permissions.require(user.permissions, permissions.MODERATE)
    solution = await db.get(Solution, solution_id)
    if solution is None:
        raise HTTPException(status_code=404, detail="Solution not found")
    solution.is_hidden = True
    solution.hidden_by_user_id = user.id
    solution.hidden_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    await db.commit()
    return {"id": solution.id, "is_hidden": solution.is_hidden}


@router.get("/users/{uid}")
async def member_profile(
    uid: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """One member's page.

    The topic breakdown is the part its owner can hide. Hidden means hidden: an
    administrator browsing profiles gets the same answer, and reaches the rows
    through the database if they must. Publicly, that is a fact about the page,
    not about the reader, so it belongs here rather than in a template.
    """
    from app.services import metrics as metrics_service

    # A card links by uid, which survives a rename; a typed name still works,
    # because a person reading a URL should not have to know that.
    target = (await db.execute(select(User).where(User.uid == uid))).scalars().first()
    if target is None:
        target = (await db.execute(select(User).where(User.username == uid))).scalars().first()
    if target is None or (target.status != "active" and not user.is_system_admin):
        raise HTTPException(status_code=404, detail="No such member")

    is_self = target.id == user.id
    show = is_self or not target.progress_private
    return {
        "username": target.username,
        "uid": target.uid,
        "bio": target.bio,
        "avatar_url": f"/media/{target.avatar_path}" if target.avatar_path else None,
        "is_self": is_self,
        "show_breakdown": show,
        "breakdown_hidden_message": None
        if show
        else "This member keeps their topic breakdown private.",
        "progress": await library_service.progress_for(db, target),
        "mastery": (await metrics_service.topic_mastery(db, target.id))["subjects"]
        if show
        else None,
        # Their history and their writing: what a member page is for.
        "recent": [
            {"id": item["id"], "topic_id": item["topic_id"], "body": item["body"]}
            for item in await library_service.recently_answered(db, target, limit=6)
        ],
        "authored": [
            {"id": item["id"], "topic_id": item["topic_id"], "body": item["body"]}
            for item in await library_service.newest_questions(
                db, user, limit=6, author_id=target.id
            )
        ],
    }


class LayoutBody(BaseModel):
    layout: str = Field(min_length=1)
    saved_at: int = Field(ge=0)


@router.get("/workspace/layout")
async def read_layout(user: User = Depends(require_user), db: AsyncSession = Depends(get_db)):
    """The arrangement this member left on any machine, if there is one."""
    from app.services import layouts as layout_service

    return await layout_service.read(db, user.id) or {"layout": None, "saved_at": 0}


@router.put("/workspace/layout")
async def save_layout(
    request: Request,
    body: LayoutBody,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Store an arrangement, unless a newer one is already here."""
    from app.services import layouts as layout_service

    check_csrf(request)
    try:
        return await layout_service.save(db, user.id, body.layout, body.saved_at)
    except ValueError as problem:
        raise HTTPException(status_code=413, detail=str(problem)) from problem


@router.get("/me/progress")
async def progress(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return await library_service.progress_for(db, user)


async def _solution_for_reader(
    db: AsyncSession, solution_id: int, viewer: User
) -> tuple[Solution, object]:
    """A visible solution, if this viewer has earned the right to be in its thread."""
    solution = await db.get(Solution, solution_id)
    if solution is None:
        raise HTTPException(status_code=404, detail="No such solution")
    if solution.is_hidden:
        raise HTTPException(status_code=404, detail="No such solution")
    author = await db.get(User, solution.author_user_id)
    if author is None or author.status != "active":
        raise HTTPException(status_code=404, detail="No such solution")
    if not await library_service.may_see_solutions(db, solution.question_id, viewer):
        raise HTTPException(
            status_code=403, detail="Answer the question before replying to its solutions"
        )
    return solution, author


@router.post("/solutions/{solution_id}/replies", status_code=201)
async def reply_to_solution(
    solution_id: int,
    request: Request,
    body: ReplyBody,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    permissions.require(user.permissions, permissions.ANSWER_QUESTION)
    solution, _ = await _solution_for_reader(db, solution_id, user)
    reply = await thread_service.add_reply(db, solution, user, body.body, body.parent_id)
    return {"id": reply.id, "parent_id": reply.parent_id, "solution_id": reply.solution_id}


@router.put("/replies/{reply_id}")
async def edit_reply(
    reply_id: int,
    request: Request,
    body: ReplyBody,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    reply = await db.get(Reply, reply_id)
    if reply is None:
        raise HTTPException(status_code=404, detail="No such reply")
    await thread_service.update_reply(db, reply, user, body.body)
    return {"id": reply.id, "body": reply.body}


@router.delete("/replies/{reply_id}", status_code=204)
async def delete_reply(
    reply_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    reply = await db.get(Reply, reply_id)
    if reply is None:
        raise HTTPException(status_code=404, detail="No such reply")
    await thread_service.delete_reply(db, reply, user)
    return Response(status_code=204)


@router.post("/solutions/{solution_id}/vote")
async def vote_on_solution(
    solution_id: int,
    request: Request,
    body: VoteBody,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    solution, _ = await _solution_for_reader(db, solution_id, user)
    return await thread_service.vote_solution(db, solution, user, body.direction)


@router.post("/replies/{reply_id}/vote")
async def vote_on_reply(
    reply_id: int,
    request: Request,
    body: VoteBody,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    reply = await db.get(Reply, reply_id)
    if reply is None:
        raise HTTPException(status_code=404, detail="No such reply")
    await _solution_for_reader(db, reply.solution_id, user)
    return await thread_service.vote_reply(db, reply, user, body.direction)
