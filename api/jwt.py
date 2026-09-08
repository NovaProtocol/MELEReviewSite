from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import jwt

from api.config import get_config

ISS = "MELEReview"
AUD = "account"
ALG = "HS256"


def _secret(secret: str | None = None) -> str:
    if secret:
        return secret
    return get_config().SECRET_KEY


def _base_payload(expires_seconds: int) -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc)
    return {
        "iss": ISS,
        "aud": AUD,
        "iat": now,
        "exp": now + dt.timedelta(seconds=expires_seconds),
        "jti": uuid.uuid4().hex,
    }


def create_session_token(account_id: int, secret: str | None = None, expires_seconds: int = 30 * 24 * 3600) -> str:
    sec = _secret(secret)
    payload = {**_base_payload(expires_seconds), "account_id": account_id}
    return jwt.encode(payload, sec, algorithm=ALG)


def verify_session_token(token: str | None, secret: str | None = None) -> dict[str, Any] | None:
    if not token:
        return None
    sec = _secret(secret)
    try:
        data = jwt.decode(token, sec, algorithms=[ALG], audience=AUD, issuer=ISS)
        if "account_id" not in data:
            return None
        return data
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    except Exception:
        return None


def decode_without_verify(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except Exception:
        return None
