from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import permissions
from app.config import get_config
from app.db import get_db
from app.models import User
from app.routes.search import results_for
from app.services import invites as invite_service
from app.services import library as library_service
from app.services import taxonomy
from app.services import users as user_service
from app.templating import render

router = APIRouter()


async def _viewer(request: Request, db: AsyncSession) -> User | None:
    """The signed-in user, or the reason the page should redirect instead."""
    from app.auth import SESSION_COOKIE
    from app.models import User as UserModel
    from app.security import read_session_token

    token = request.cookies.get(SESSION_COOKIE)
    user_id = read_session_token(token)
    if user_id is None:
        return None
    user = await db.get(UserModel, user_id)
    request.state.viewer = user
    return user


def _blocked(user: User | None) -> bool:
    return user is not None and user.status != "active"


@router.get("/")
async def landing(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _viewer(request, db)
    if user is not None and user.status == "active":
        return RedirectResponse("/library", status_code=302)
    if _blocked(user):
        return RedirectResponse("/status", status_code=302)
    subjects = await library_service.list_subjects(db)
    return render(request, "landing.html", {"subjects": subjects, "anon": True})


@router.get("/register")
async def register_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _viewer(request, db)
    if user is not None and user.status == "active":
        return RedirectResponse("/library", status_code=302)
    if _blocked(user):
        return RedirectResponse("/status", status_code=302)
    code = request.query_params.get("code", "")
    return render(request, "register.html", {"code": code, "anon": True})


@router.get("/status")
async def status_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _viewer(request, db)
    if user is None:
        return RedirectResponse("/", status_code=302)
    if user.status == "active":
        return RedirectResponse("/library", status_code=302)
    root = await db.get(User, user.status_root_user_id) if user.status_root_user_id else None
    return render(
        request,
        "status.html",
        {"viewer": user, "root": root, "anon": True},
    )


@router.get("/library")
async def library_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _viewer(request, db)
    if user is None:
        return RedirectResponse("/", status_code=302)
    if user.status != "active":
        return RedirectResponse("/status", status_code=302)
    subjects = await library_service.list_subjects(db)
    return render(
        request,
        "library.html",
        {
            "viewer": user,
            "subjects": subjects,
            "progress": await library_service.progress_for(db, user),
            "popular_tags": await taxonomy.list_tags(db, with_counts=True),
        },
    )


@router.get("/search")
async def search_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Member search. Rendered server-side so the results survive a refresh."""
    user = await _viewer(request, db)
    if user is None:
        return RedirectResponse("/", status_code=302)
    if user.status != "active":
        return RedirectResponse("/status", status_code=302)

    term = request.query_params.get("q", "").strip()
    # Accept both forms: `?tags=a,b` from a link and `?tags=a&tags=b` from the
    # checkbox fieldset, which is what a browser submits.
    selected = [
        part.strip()
        for value in request.query_params.getlist("tags")
        for part in value.split(",")
        if part.strip()
    ]
    subject = request.query_params.get("subject") or ""
    results: list[dict] = []
    suggested: list[str] = []
    if term or selected:
        questions = await taxonomy.search_questions(
            db,
            term=term,
            tags=selected,
            subject_id=int(subject) if subject.isdigit() else None,
        )
        results = await results_for(db, questions, with_stats=False)
        if term:
            suggested = await taxonomy.tag_suggestions(db, term)

    return render(
        request,
        "search.html",
        {
            "viewer": user,
            "term": term,
            "selected_tags": selected,
            "selected_subject": subject,
            "subjects": await library_service.list_subjects(db),
            "tags": await taxonomy.list_tags(db, with_counts=True),
            "results": results,
            "suggested_tags": suggested,
            "searched": bool(term or selected),
        },
    )


@router.get("/topics/{topic_id}")
async def topic_page(request: Request, topic_id: int, db: AsyncSession = Depends(get_db)):
    user = await _viewer(request, db)
    if user is None:
        return RedirectResponse("/", status_code=302)
    if user.status != "active":
        return RedirectResponse("/status", status_code=302)
    topic, subject = await library_service.get_topic(db, topic_id)
    return render(
        request,
        "topic.html",
        {"viewer": user, "topic": topic, "subject": subject},
    )


@router.get("/topics/{topic_id}/{question_id}")
async def question_page(
    request: Request,
    topic_id: int,
    question_id: int,
    db: AsyncSession = Depends(get_db),
):
    """One question, full page: the statement, the choices, then the solutions."""
    user = await _viewer(request, db)
    if user is None:
        return RedirectResponse("/", status_code=302)
    if user.status != "active":
        return RedirectResponse("/status", status_code=302)
    question = await library_service.get_question(db, question_id)
    if question.topic_id != topic_id:
        raise HTTPException(status_code=404, detail="Question not found")
    topic, subject = await library_service.get_topic(db, topic_id)
    include_hidden = permissions.has(user.permissions, permissions.VIEW_HIDDEN)
    if question.is_hidden and not include_hidden:
        raise HTTPException(status_code=404, detail="Question not found")
    return render(
        request,
        "question.html",
        {
            "viewer": user,
            "topic": topic,
            "subject": subject,
            "question_id": question_id,
        },
    )


@router.get("/questions/new")
async def question_new(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _viewer(request, db)
    if user is None:
        return RedirectResponse("/", status_code=302)
    if user.status != "active":
        return RedirectResponse("/status", status_code=302)
    if not permissions.has(user.permissions, permissions.POST_QUESTION):
        raise HTTPException(status_code=403, detail="You cannot post questions")
    subjects = await library_service.list_subjects(db)
    return render(
        request,
        "question_form.html",
        {"viewer": user, "subjects": subjects, "question": None},
    )


@router.get("/questions/{question_id}/edit")
async def question_edit(request: Request, question_id: int, db: AsyncSession = Depends(get_db)):
    user = await _viewer(request, db)
    if user is None:
        return RedirectResponse("/", status_code=302)
    if user.status != "active":
        return RedirectResponse("/status", status_code=302)
    question = await library_service.get_question(db, question_id)
    if question.author_user_id != user.id and not permissions.has(
        user.permissions, permissions.MODERATE
    ):
        raise HTTPException(status_code=403, detail="Not your question")
    subjects = await library_service.list_subjects(db)
    tags = (await taxonomy.tags_for_questions(db, [question.id])).get(question.id, [])
    return render(
        request,
        "question_form.html",
        {"viewer": user, "subjects": subjects, "question": question, "tags": tags},
    )


@router.get("/users/{username}")
async def user_page(request: Request, username: str, db: AsyncSession = Depends(get_db)):
    """Another member's public numbers, and their own page when it is them."""
    user = await _viewer(request, db)
    if user is None:
        return RedirectResponse("/", status_code=302)
    if user.status != "active":
        return RedirectResponse("/status", status_code=302)
    target = await user_service.get_by_login(db, username)
    if target is None or target.status != "active":
        raise HTTPException(status_code=404, detail="No such member")
    return render(
        request,
        "user.html",
        {
            "viewer": user,
            "member": target,
            "is_self": target.id == user.id,
            "progress": await library_service.progress_for(db, target),
        },
    )


@router.get("/profile")
async def profile_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _viewer(request, db)
    if user is None:
        return RedirectResponse("/", status_code=302)
    if user.status != "active":
        return RedirectResponse("/status", status_code=302)
    inviter = await db.get(User, user.invited_by_user_id) if user.invited_by_user_id else None
    return render(
        request,
        "profile.html",
        {
            "viewer": user,
            "inviter": inviter,
            "progress": await library_service.progress_for(db, user),
            "recent": await library_service.recently_answered(db, user, limit=8),
            "newest": await library_service.newest_questions(db, user, limit=8),
            "invites": await invite_service.list_invites(db, user)
            if permissions.has(user.permissions, permissions.INVITE)
            else [],
            "invite_limit": get_config().MAX_OPEN_INVITES,
        },
    )


@router.get("/admin")
async def admin_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _viewer(request, db)
    if user is None:
        return RedirectResponse("/", status_code=302)
    if user.status != "active":
        return RedirectResponse("/status", status_code=302)
    if not user.is_system_admin:
        raise HTTPException(status_code=403, detail="System administrator only")
    users, total = await user_service.list_users(db, per_page=100)
    inviter_ids = {u.invited_by_user_id for u in users if u.invited_by_user_id}
    inviter_names: dict[int, str] = {}
    if inviter_ids:
        rows = await db.execute(select(User.id, User.username).where(User.id.in_(inviter_ids)))
        inviter_names = {row[0]: row[1] for row in rows.all()}
    return render(
        request,
        "admin.html",
        {
            "viewer": user,
            "users": users,
            "user_total": total,
            "inviter_names": inviter_names,
            "counts": await user_service.counts_by_status(db),
            "subjects": await library_service.list_subjects(db),
            "hidden": await library_service.hidden_content(db),
            "all_invites": await invite_service.list_invites(db, user, all_users=True),
        },
    )
