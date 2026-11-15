"""Reply threads and votes on solutions.

A solution is the top of a thread; replies hang off it, and off each other, to
any depth. Votes are per member and the score is their sum, the same rule the
questions use.
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Reply, ReplyVote, Solution, SolutionVote, User

MAX_REPLY = 4000


async def _solution_votes(
    db: AsyncSession, solution_ids: list[int], viewer: User | None
) -> dict[int, dict]:
    if not solution_ids:
        return {}
    rows = await db.execute(
        select(
            SolutionVote.solution_id,
            func.coalesce(func.sum(SolutionVote.vote), 0),
        )
        .where(SolutionVote.solution_id.in_(solution_ids))
        .group_by(SolutionVote.solution_id)
    )
    scores = {sid: int(score or 0) for sid, score in rows.all()}
    mine: dict[int, int] = {}
    if viewer is not None:
        own = await db.execute(
            select(SolutionVote.solution_id, SolutionVote.vote).where(
                SolutionVote.solution_id.in_(solution_ids),
                SolutionVote.user_id == viewer.id,
            )
        )
        mine = {sid: int(value) for sid, value in own.all()}
    return {sid: {"score": scores.get(sid, 0), "my_vote": mine.get(sid, 0)} for sid in solution_ids}


async def _reply_votes(
    db: AsyncSession, reply_ids: list[int], viewer: User | None
) -> dict[int, dict]:
    if not reply_ids:
        return {}
    rows = await db.execute(
        select(ReplyVote.reply_id, func.coalesce(func.sum(ReplyVote.vote), 0))
        .where(ReplyVote.reply_id.in_(reply_ids))
        .group_by(ReplyVote.reply_id)
    )
    scores = {rid: int(score or 0) for rid, score in rows.all()}
    mine: dict[int, int] = {}
    if viewer is not None:
        own = await db.execute(
            select(ReplyVote.reply_id, ReplyVote.vote).where(
                ReplyVote.reply_id.in_(reply_ids), ReplyVote.user_id == viewer.id
            )
        )
        mine = {rid: int(value) for rid, value in own.all()}
    return {rid: {"score": scores.get(rid, 0), "my_vote": mine.get(rid, 0)} for rid in reply_ids}


async def attach_threads(db: AsyncSession, solutions: list[dict], viewer: User | None) -> None:
    """Fill in scores and the reply tree for a list of solution payloads."""
    if not solutions:
        return
    solution_ids = [item["id"] for item in solutions]
    votes = await _solution_votes(db, solution_ids, viewer)

    rows = (
        await db.execute(
            select(Reply, User.username, User.uid, User.status)
            .join(User, User.id == Reply.author_user_id)
            .where(Reply.solution_id.in_(solution_ids))
            .order_by(Reply.date_created, Reply.id)
        )
    ).all()

    reply_votes = await _reply_votes(db, [row[0].id for row in rows], viewer)

    nodes: dict[int, dict] = {}
    for reply, username, uid, author_status in rows:
        # A banned or revoked author's replies stay in the table and drop out of
        # the thread, the same way their questions leave the library.
        if author_status != "active":
            continue
        node = {
            "id": reply.id,
            "solution_id": reply.solution_id,
            "parent_id": reply.parent_id,
            "body": reply.body,
            "author": username,
            "author_uid": uid,
            "date_created": reply.date_created.isoformat(),
            "score": reply_votes.get(reply.id, {}).get("score", 0),
            "my_vote": reply_votes.get(reply.id, {}).get("my_vote", 0),
            # Whoever may delete a reply may rewrite it, so one flag covers both.
            "can_edit": bool(
                viewer is not None and (reply.author_user_id == viewer.id or viewer.is_system_admin)
            ),
            "replies": [],
        }
        nodes[reply.id] = node

    roots: dict[int, list[dict]] = {}
    for node in nodes.values():
        parent = nodes.get(node["parent_id"]) if node["parent_id"] else None
        if parent is not None:
            parent["replies"].append(node)
        else:
            # A reply whose parent dropped out (its author was banned, say) is
            # lifted to the top of the thread rather than disappearing with it.
            roots.setdefault(node["solution_id"], []).append(node)

    for item in solutions:
        item.update(votes.get(item["id"], {"score": 0, "my_vote": 0}))
        item["replies"] = roots.get(item["id"], [])


async def add_reply(
    db: AsyncSession,
    solution: Solution,
    author: User,
    body: str,
    parent_id: int | None,
) -> Reply:
    text = (body or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="A reply cannot be empty")
    if len(text) > MAX_REPLY:
        raise HTTPException(status_code=422, detail=f"Keep a reply under {MAX_REPLY} characters")

    if parent_id is not None:
        parent = await db.get(Reply, parent_id)
        if parent is None or parent.solution_id != solution.id:
            raise HTTPException(status_code=404, detail="No such reply in this thread")

    reply = Reply(
        solution_id=solution.id,
        parent_id=parent_id,
        author_user_id=author.id,
        body=text,
    )
    db.add(reply)
    await db.commit()
    await db.refresh(reply)
    return reply


async def update_reply(db: AsyncSession, reply: Reply, actor: User, body: str) -> Reply:
    if reply.author_user_id != actor.id and not actor.is_system_admin:
        raise HTTPException(status_code=403, detail="Not your reply")
    text = (body or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="A reply cannot be empty")
    if len(text) > MAX_REPLY:
        raise HTTPException(status_code=422, detail=f"Keep a reply under {MAX_REPLY} characters")
    reply.body = text
    await db.commit()
    await db.refresh(reply)
    return reply


async def delete_reply(db: AsyncSession, reply: Reply, actor: User) -> None:
    if reply.author_user_id != actor.id and not actor.is_system_admin:
        raise HTTPException(status_code=403, detail="Not your reply")
    await db.delete(reply)
    await db.commit()


async def _set_vote(db: AsyncSession, model, key: str, target_id: int, user: User, value: int):
    value = 0 if value not in (-1, 0, 1) else value
    column = model.__table__.c[key]
    row = (
        (await db.execute(select(model).where(column == target_id, model.user_id == user.id)))
        .scalars()
        .first()
    )
    if row is None:
        if value:
            db.add(model(**{key: target_id, "user_id": user.id, "vote": value}))
    else:
        row.vote = value
    await db.commit()


async def vote_solution(db: AsyncSession, solution: Solution, user: User, value: int) -> dict:
    await _set_vote(db, SolutionVote, "solution_id", solution.id, user, value)
    votes = await _solution_votes(db, [solution.id], user)
    return votes[solution.id]


async def vote_reply(db: AsyncSession, reply: Reply, user: User, value: int) -> dict:
    await _set_vote(db, ReplyVote, "reply_id", reply.id, user, value)
    votes = await _reply_votes(db, [reply.id], user)
    return votes[reply.id]
