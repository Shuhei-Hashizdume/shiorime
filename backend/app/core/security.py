"""パスワードのハッシュ化・JWT・ログインの Cookie（notes.md 3章、api.md 3章）。"""

import uuid
from datetime import datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash
from starlette.responses import Response

from app.core.config import settings

# ---- パスワード（Argon2id） ----

_password_hash = PasswordHash.recommended()

# 存在しないメールアドレスでログインされたときも、同じ重さの計算をするためのダミー（api.md 5-2）
_DUMMY_HASH = _password_hash.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


def verify_dummy_password(password: str) -> None:
    """結果は使わない。返事の速さを、ユーザーがいる場合とそろえるためだけに計算する。"""
    _password_hash.verify(password, _DUMMY_HASH)


# ---- JWT ----

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_LIFETIME = timedelta(days=7)


def create_access_token(user_id: uuid.UUID, token_version: int, now: datetime) -> str:
    payload = {
        "sub": str(user_id),
        "ver": token_version,
        "iat": now,
        "exp": now + ACCESS_TOKEN_LIFETIME,
    }
    return jwt.encode(payload, settings.jwt_secret_key.get_secret_value(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """署名と期限を確かめて中身を返す。

    期限切れは jwt.ExpiredSignatureError、それ以外の不正は jwt.InvalidTokenError を投げる。
    """
    return jwt.decode(
        token,
        settings.jwt_secret_key.get_secret_value(),
        algorithms=[JWT_ALGORITHM],
        options={"require": ["exp", "sub", "ver"]},
    )


# ---- Cookie ----

AUTH_COOKIE_NAME = "access_token"
# Cookie は30日残し、7日で切れた JWT が届いたとわかるようにする（api.md 3-3）
AUTH_COOKIE_MAX_AGE = int(timedelta(days=30).total_seconds())

_COOKIE_ATTRIBUTES: dict[str, Any] = {
    "path": "/",
    "httponly": True,
    "secure": True,
    "samesite": "lax",
}


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(AUTH_COOKIE_NAME, token, max_age=AUTH_COOKIE_MAX_AGE, **_COOKIE_ATTRIBUTES)


def clear_auth_cookie(response: Response) -> None:
    """発行したときと同じ属性で消す（notes.md 3章）。"""
    response.delete_cookie(AUTH_COOKIE_NAME, **_COOKIE_ATTRIBUTES)
