"""routers が Depends で使う部品。"""

import uuid
from typing import Annotated

import jwt
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import AUTH_COOKIE_NAME, decode_access_token
from app.db import get_db
from app.models import User

DbSession = Annotated[Session, Depends(get_db)]


def _unauthenticated(*, clear_cookie: bool) -> AppError:
    return AppError(401, "UNAUTHENTICATED", "ログインしていません", clear_auth_cookie=clear_cookie)


def get_current_user(request: Request, db: DbSession) -> User:
    """Cookie の JWT を確かめ、ログイン中のユーザーを返す（認証。api.md 3-3）。"""
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        raise _unauthenticated(clear_cookie=False)

    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise AppError(
            401, "TOKEN_EXPIRED", "ログインの有効期限が切れました", clear_auth_cookie=True
        ) from None
    except jwt.InvalidTokenError:
        raise _unauthenticated(clear_cookie=True) from None

    try:
        user_id = uuid.UUID(str(payload["sub"]))
        token_version = int(payload["ver"])
    except (ValueError, TypeError):
        raise _unauthenticated(clear_cookie=True) from None

    user = db.get(User, user_id)
    if user is None:
        # 期限内の JWT でも、退会済みなら断る（notes.md 3章）
        raise _unauthenticated(clear_cookie=True)

    if user.token_version != token_version:
        # パスワードの変更で、それより前の JWT は使えない
        raise AppError(
            401, "TOKEN_REVOKED", "パスワードが変更されたため、ログインし直してください", clear_auth_cookie=True
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
