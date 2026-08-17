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
    account = Account(name=data.name.strip(), pin=data.pin)
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
