"""Password hashing and session tokens.

Passwords use stdlib scrypt with a per-user salt; the stored string carries its
own parameters so the cost can be raised later without invalidating old rows.
Sessions are HS256 JWTs that only name the user id: every request re-reads the
row, so a ban takes effect on the next request instead of when the token expires.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import secrets
import uuid

import jwt

from app.config import get_config

ISS = "MELEReview"
AUD = "account"
ALG = "HS256"

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
DKLEN = 32
SALT_BYTES = 16
SESSION_DAYS = 30


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=DKLEN,
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(derived)}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        scheme, n_raw, r_raw, p_raw, salt_raw, hash_raw = stored.split("$")
        if scheme != "scrypt":
            return False
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_unb64(salt_raw),
            n=int(n_raw),
            r=int(r_raw),
            p=int(p_raw),
            dklen=len(_unb64(hash_raw)),
        )
    except ValueError, TypeError:
        return False
    return hmac.compare_digest(derived, _unb64(hash_raw))


def new_uid() -> str:
    return uuid.uuid4().hex


def create_session_token(user_id: int, secret: str | None = None) -> str:
    now = dt.datetime.now(dt.UTC)
    payload = {
        "iss": ISS,
        "aud": AUD,
        "iat": now,
        "exp": now + dt.timedelta(days=SESSION_DAYS),
        "jti": uuid.uuid4().hex,
        "user_id": user_id,
    }
    token: str = jwt.encode(payload, secret or get_config().SECRET_KEY, algorithm=ALG)
    return token


def read_session_token(token: str | None, secret: str | None = None) -> int | None:
    if not token:
        return None
    try:
        data = jwt.decode(
            token,
            secret or get_config().SECRET_KEY,
            algorithms=[ALG],
            audience=AUD,
            issuer=ISS,
        )
        return int(data["user_id"])
    except jwt.InvalidTokenError, KeyError, TypeError, ValueError:
        return None


def new_csrf_token() -> str:
    return secrets.token_urlsafe(24)


def tokens_match(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return hmac.compare_digest(a, b)


def new_invite_code() -> str:
    return secrets.token_hex(8)
