from __future__ import annotations

import hmac

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import permissions
from app.config import get_config
from app.models import User
from app.security import hash_password, new_uid, verify_password

USERNAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")


def normalise_username(raw: str) -> str:
    value = raw.strip()
    if not 3 <= len(value) <= 32:
        raise HTTPException(status_code=422, detail="Username must be 3 to 32 characters")
    if any(char not in USERNAME_CHARS for char in value):
        raise HTTPException(
            status_code=422,
            detail="Username may use letters, digits, underscore, dot and hyphen",
        )
    return value


def normalise_email(raw: str) -> str:
    value = raw.strip().lower()
    if "@" not in value or len(value) > 254 or value.startswith("@") or value.endswith("@"):
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    return value


async def get_user(db: AsyncSession, user_id: int) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def get_by_login(db: AsyncSession, identifier: str) -> User | None:
    value = identifier.strip()
    if not value:
        return None
    stmt = select(User).where(
        or_(User.username == value, User.email == value.lower(), User.uid == value)
    )
    return (await db.execute(stmt)).scalars().first()


async def create_user(
    db: AsyncSession,
    username: str,
    email: str,
    password: str,
    invited_by_user_id: int | None = None,
    permissions_mask: int | None = None,
) -> User:
    name = normalise_username(username)
    address = normalise_email(email)
    if len(password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")
    taken = (
        (await db.execute(select(User).where(or_(User.username == name, User.email == address))))
        .scalars()
        .first()
    )
    if taken is not None:
        field = "Username" if taken.username == name else "Email"
        raise HTTPException(status_code=409, detail=f"{field} is already registered")
    user = User(
        uid=new_uid(),
        username=name,
        email=address,
        password_hash=hash_password(password),
        permissions=permissions.DEFAULT if permissions_mask is None else permissions_mask,
        invited_by_user_id=invited_by_user_id,
    )
    db.add(user)
    await db.flush()
    return user


async def authenticate(db: AsyncSession, identifier: str, password: str) -> User:
    user = await get_by_login(db, identifier)
    if user is None:
        raise HTTPException(status_code=401, detail="Wrong username or password")

    if user.is_system_admin:
        # The administrator's password is ADMIN_PASS and nothing else. The table
        # holds no hash for it, and a hash planted there is not accepted either,
        # so a database leak yields no usable administrator credential.
        config = get_config()
        known = {config.ADMIN_USER, user.username, user.email}
        if not (identifier in known and hmac.compare_digest(password, config.ADMIN_PASS)):
            raise HTTPException(status_code=401, detail="Wrong username or password")
    elif not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Wrong username or password")
    if user.status != "active":
        raise HTTPException(status_code=403, detail=user.status)
    return user


async def set_username(db: AsyncSession, user: User, username: str) -> User:
    name = normalise_username(username)
    clash = (await db.execute(select(User).where(User.username == name))).scalars().first()
    if clash is not None and clash.id != user.id:
        raise HTTPException(status_code=409, detail="Username is already taken")
    user.username = name
    await db.commit()
    await db.refresh(user)
    return user


async def set_email(db: AsyncSession, user: User, email: str) -> User:
    address = normalise_email(email)
    clash = (await db.execute(select(User).where(User.email == address))).scalars().first()
    if clash is not None and clash.id != user.id:
        raise HTTPException(status_code=409, detail="Email is already registered")
    user.email = address
    await db.commit()
    await db.refresh(user)
    return user


async def set_password(db: AsyncSession, user: User, current: str | None, new: str) -> None:
    """Set a password.

    ``current`` is the old password, and is checked. ``None`` means an
    administrator is setting it for someone else, which they cannot know.
    """
    if user.is_system_admin and user.password_hash is None:
        # Its password is the environment's, re-applied on every boot. Writing a
        # hash here would be a credential the database leak could yield, and it
        # would be overwritten at the next start anyway.
        raise HTTPException(
            status_code=409,
            detail="The administrator password is set by ADMIN_PASS, not in the app",
        )
    if current is not None and not verify_password(current, user.password_hash):
        raise HTTPException(status_code=403, detail="Current password is wrong")
    if len(new) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")
    user.password_hash = hash_password(new)
    await db.commit()


async def set_bio(db: AsyncSession, user: User, bio: str) -> User:
    user.bio = bio.strip()[:500] or None
    await db.commit()
    await db.refresh(user)
    return user


async def set_permissions(db: AsyncSession, user: User, mask: int) -> User:
    user.permissions = mask & permissions.ALL
    await db.commit()
    await db.refresh(user)
    return user


async def list_users(
    db: AsyncSession, search: str = "", status: str = "", page: int = 1, per_page: int = 50
) -> tuple[list[User], int]:
    conditions = []
    if search.strip():
        term = f"%{search.strip()}%"
        conditions.append(or_(User.username.like(term), User.email.like(term), User.uid.like(term)))
    if status.strip():
        conditions.append(User.status == status.strip())
    query = select(User)
    count = select(func.count()).select_from(User)
    if conditions:
        query = query.where(*conditions)
        count = count.where(*conditions)
    total = int((await db.execute(count)).scalar_one())
    rows = await db.execute(query.order_by(User.id).offset((page - 1) * per_page).limit(per_page))
    return list(rows.scalars().all()), total


async def counts_by_status(db: AsyncSession) -> dict[str, int]:
    rows = await db.execute(select(User.status, func.count()).group_by(User.status))
    counts = {status: int(count) for status, count in rows.all()}
    for key in ("active", "banned", "revoked"):
        counts.setdefault(key, 0)
    return counts
