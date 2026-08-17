from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeSerializer
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_config
from api.db import get_db
from api.models import Account
from api.schemas import AccountCreate, AccountLogin, AccountOut
from api.services import account_service

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_NAME = "session"


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(get_config().SECRET_KEY)


def create_session_cookie(account_id: int) -> str:
    return _serializer().dumps({"account_id": account_id})


def read_session_cookie(cookie_value: str) -> int | None:
    try:
        data = _serializer().loads(cookie_value)
        return int(data.get("account_id"))
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None


async def get_current_account(request: Request, db: AsyncSession = Depends(get_db)) -> Account:
    cookie = request.cookies.get(COOKIE_NAME)
    account_id = read_session_cookie(cookie) if cookie else None
    if account_id is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    account = await db.get(Account, account_id)
    if not account or account.disabled:
        raise HTTPException(status_code=401, detail="Not logged in")
    return account


@router.get("/accounts", response_model=list[AccountOut])
async def list_accounts(db: AsyncSession = Depends(get_db)):
    return await account_service.list_accounts(db)


@router.post("/accounts", response_model=AccountOut, status_code=201)
async def create_account(body: AccountCreate, db: AsyncSession = Depends(get_db)):
    return await account_service.create_account(db, body)


@router.post("/login")
async def login(body: AccountLogin, response: Response, db: AsyncSession = Depends(get_db)):
    account = await account_service.verify_login(db, body.account_id, body.pin)
    response.set_cookie(COOKIE_NAME, create_session_cookie(account.id), httponly=True, samesite="lax")
    return {"id": account.id, "name": account.name}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.get("/me", response_model=AccountOut)
async def me(account: Account = Depends(get_current_account)):
    return account


@router.delete("/me", status_code=204)
async def delete_me(
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete: disable the account. Content stays."""
    account.disabled = True
    await db.commit()
    return Response(status_code=204)
