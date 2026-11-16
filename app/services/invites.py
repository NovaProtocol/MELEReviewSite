"""The invitation chain.

Every account except the system administrator was created by redeeming a code, and
the code records who minted it. That single column is the chain: banning a user
walks it downward and revokes everyone underneath, so a compromised account cannot
keep a hidden audience alive.

Revocation is deliberately different from a ban. A banned user sees that they were
banned. A revoked user sees whose action took their access away and is told they
need a new invitation. Neither loses data: content stays in the rows, and the
public queries filter by author status, so the cascade writes only ``users`` and
``invites``, never thousands of content rows.
"""

from __future__ import annotations

import datetime as dt

from fastapi import HTTPException
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import permissions
from app.config import get_config
from app.models import Invite, Question, Solution, User
from app.security import new_invite_code
from app.services import users as user_service

# One recursive walk over invited_by_user_id. MySQL 8.4 and SQLite both support it.
DESCENDANTS_SQL = """
WITH RECURSIVE chain (id) AS (
    SELECT :root_id
    UNION ALL
    SELECT u.id FROM users u JOIN chain c ON u.invited_by_user_id = c.id
)
SELECT id FROM chain WHERE id <> :root_id
"""


async def descendants(db: AsyncSession, user_id: int) -> list[int]:
    result = await db.execute(text(DESCENDANTS_SQL), {"root_id": user_id})
    return [int(row[0]) for row in result.all()]


async def direct_invitee_count(db: AsyncSession, user_id: int) -> int:
    return int(
        (
            await db.execute(
                select(func.count()).select_from(User).where(User.invited_by_user_id == user_id)
            )
        ).scalar_one()
    )


async def content_counts(db: AsyncSession, user_ids: list[int]) -> tuple[int, int]:
    if not user_ids:
        return 0, 0
    questions = int(
        (
            await db.execute(
                select(func.count())
                .select_from(Question)
                .where(Question.author_user_id.in_(user_ids))
            )
        ).scalar_one()
    )
    solutions = int(
        (
            await db.execute(
                select(func.count())
                .select_from(Solution)
                .where(Solution.author_user_id.in_(user_ids))
            )
        ).scalar_one()
    )
    return questions, solutions


async def create_invite(db: AsyncSession, user: User) -> Invite:
    permissions.require(user.permissions, permissions.INVITE)
    limit = get_config().MAX_OPEN_INVITES
    open_codes = int(
        (
            await db.execute(
                select(func.count())
                .select_from(Invite)
                .where(
                    Invite.created_by_user_id == user.id,
                    Invite.used_by_user_id.is_(None),
                    Invite.revoked_at.is_(None),
                )
            )
        ).scalar_one()
    )
    if open_codes >= limit:
        raise HTTPException(
            status_code=409,
            detail=f"You already have {open_codes} unused invitations; {limit} is the limit",
        )
    invite = Invite(code=new_invite_code(), created_by_user_id=user.id)
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    return invite


async def register(db: AsyncSession, code: str, username: str, email: str, password: str) -> User:
    invite = (
        (await db.execute(select(Invite).where(Invite.code == code.strip().lower())))
        .scalars()
        .first()
    )
    if invite is None or invite.used_by_user_id is not None or invite.revoked_at is not None:
        raise HTTPException(status_code=400, detail="That invitation code is not usable")
    creator = await db.get(User, invite.created_by_user_id)
    if creator is None or creator.status != "active":
        raise HTTPException(
            status_code=400,
            detail="The person who issued that code no longer has access",
        )
    user = await user_service.create_user(
        db,
        username=username,
        email=email,
        password=password,
        invited_by_user_id=creator.id,
    )
    invite.used_by_user_id = user.id
    invite.used_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    await db.commit()
    await db.refresh(user)
    return user


async def ban_preview(db: AsyncSession, user_id: int) -> dict:
    target = await user_service.get_user(db, user_id)
    chain = await descendants(db, user_id)
    direct = await direct_invitee_count(db, user_id)
    questions, solutions = await content_counts(db, [user_id, *chain])
    open_invites = int(
        (
            await db.execute(
                select(func.count())
                .select_from(Invite)
                .where(
                    Invite.created_by_user_id.in_([user_id, *chain]),
                    Invite.used_by_user_id.is_(None),
                    Invite.revoked_at.is_(None),
                )
            )
        ).scalar_one()
    )
    return {
        "user": {"id": target.id, "username": target.username, "uid": target.uid},
        "direct_invitees": direct,
        "total_descendants": len(chain),
        "questions": questions,
        "solutions": solutions,
        "open_invites": open_invites,
    }


async def _revoke_codes(db: AsyncSession, owner_ids: list[int], actor_id: int) -> int:
    if not owner_ids:
        return 0
    result = await db.execute(
        update(Invite)
        .where(
            Invite.created_by_user_id.in_(owner_ids),
            Invite.used_by_user_id.is_(None),
            Invite.revoked_at.is_(None),
        )
        .values(
            revoked_at=dt.datetime.now(dt.UTC).replace(tzinfo=None),
            revoked_by_user_id=actor_id,
        )
    )
    rowcount = getattr(result, "rowcount", 0)
    return int(rowcount or 0)


async def ban(db: AsyncSession, target_id: int, actor: User) -> dict:
    if target_id == actor.id:
        raise HTTPException(status_code=400, detail="You cannot ban your own account")
    target = await user_service.get_user(db, target_id)
    if target.is_system_admin:
        raise HTTPException(status_code=400, detail="A system administrator cannot be banned")
    chain = await descendants(db, target_id)

    target.status = "banned"
    target.status_reason = "banned"
    target.status_root_user_id = target.id
    if chain:
        await db.execute(
            update(User)
            .where(User.id.in_(chain))
            .values(status="revoked", status_reason="revoked", status_root_user_id=target.id)
        )
    codes = await _revoke_codes(db, [target_id, *chain], actor.id)
    await db.commit()
    # Their papers go with them; the questions they wrote stay in the bank.
    from app.services import quizzes as quiz_service

    for user_id in [target_id, *chain]:
        await quiz_service.remove_for_owner(db, user_id)
    return {"banned": target_id, "revoked": len(chain), "codes_revoked": codes}


async def revoke_subtree(db: AsyncSession, target_id: int, actor: User) -> dict:
    target = await user_service.get_user(db, target_id)
    chain = await descendants(db, target_id)
    if chain:
        await db.execute(
            update(User)
            .where(User.id.in_(chain))
            .values(status="revoked", status_reason="revoked", status_root_user_id=target.id)
        )
    codes = await _revoke_codes(db, [target_id, *chain], actor.id)
    await db.commit()
    return {"kept": target_id, "revoked": len(chain), "codes_revoked": codes}


async def reactivate(db: AsyncSession, target_id: int) -> dict:
    """Restore one account. Descendants stay revoked: they need a new invitation."""
    target = await user_service.get_user(db, target_id)
    target.status = "active"
    target.status_reason = None
    target.status_root_user_id = None
    await db.commit()
    return {"reactivated": target_id}


async def invite_view(invite: Invite, creator_name: str | None = None) -> dict:
    return {
        "id": invite.id,
        "code": invite.code,
        "created_by": creator_name,
        "used_by_user_id": invite.used_by_user_id,
        "used_at": invite.used_at,
        "revoked_at": invite.revoked_at,
        "date_created": invite.date_created,
        "state": "used" if invite.used_by_user_id else ("revoked" if invite.revoked_at else "open"),
    }


async def list_invites(db: AsyncSession, user: User, all_users: bool = False) -> list[dict]:
    query = select(Invite, User.username).join(User, User.id == Invite.created_by_user_id)
    if not all_users:
        query = query.where(Invite.created_by_user_id == user.id)
    query = query.order_by(Invite.id.desc())
    rows = await db.execute(query)
    return [await invite_view(invite, name) for invite, name in rows.all()]


async def revoke_invite(db: AsyncSession, invite_id: int, actor: User) -> None:
    invite = await db.get(Invite, invite_id)
    if invite is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invite.used_by_user_id is not None:
        raise HTTPException(status_code=400, detail="That code has already been used")
    invite.revoked_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    invite.revoked_by_user_id = actor.id
    await db.commit()
