from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import Account
from api.schemas import AccountCreate


async def list_accounts(db: AsyncSession) -> list[Account]:
    result = await db.execute(
        select(Account).where(Account.disabled.is_(False)).order_by(Account.name)
    )
    return list(result.scalars().all())


async def create_account(db: AsyncSession, data: AccountCreate) -> Account:
    stripped = data.name.strip()
    if not stripped:
        raise HTTPException(status_code=422, detail="Name must not be empty or whitespace only")
    # check duplicate (case-sensitive match on stripped name)
    existing = await db.execute(select(Account).where(Account.name == stripped))
    if existing.scalars().first() is not None:
        raise HTTPException(status_code=409, detail="Account name already exists")
    account = Account(name=stripped, pin=data.pin)
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


async def get_account(db: AsyncSession, account_id: int) -> Account:
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


async def verify_login(db: AsyncSession, account_id: int, pin: str) -> Account:
    account = await db.get(Account, account_id)
    if not account or account.disabled or account.pin != pin:
        raise HTTPException(status_code=401, detail="Invalid pin")
    return account
