"""GET /api/v1/me と、ログイン状態の確かめ（api.md 3-3・7-2）。"""

import uuid
from datetime import timedelta

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core import clock
from app.core.security import AUTH_COOKIE_NAME, create_access_token
from app.models import User
from tests.helpers import register

ME_URL = "/api/v1/me"


def _assert_401(response, code: str, *, cookie_cleared: bool) -> None:
    assert response.status_code == 401
    assert response.json()["error"]["code"] == code
    set_cookie = response.headers.get("set-cookie", "")
    if cookie_cleared:
        assert set_cookie.startswith(f'{AUTH_COOKIE_NAME}=""')
        assert "Max-Age=0" in set_cookie
    else:
        assert set_cookie == ""


def _user(db: Session) -> User:
    return db.scalars(select(User)).one()


def test_me_returns_same_shape_as_register(client: TestClient) -> None:
    registered = register(client).json()

    response = client.get(ME_URL)

    assert response.status_code == 200
    assert response.json() == registered


def test_no_cookie_is_unauthenticated(client: TestClient) -> None:
    _assert_401(client.get(ME_URL), "UNAUTHENTICATED", cookie_cleared=False)


def test_expired_token(client: TestClient, db: Session) -> None:
    register(client)
    user = _user(db)
    old = create_access_token(user.id, user.token_version, clock.now() - timedelta(days=8))
    client.cookies.set(AUTH_COOKIE_NAME, old)

    _assert_401(client.get(ME_URL), "TOKEN_EXPIRED", cookie_cleared=True)


def test_token_with_old_version_is_revoked(client: TestClient, db: Session) -> None:
    register(client)
    # パスワードの変更でトークンのバージョンが上がった状態
    db.execute(update(User).values(token_version=User.token_version + 1))
    db.commit()

    _assert_401(client.get(ME_URL), "TOKEN_REVOKED", cookie_cleared=True)


def test_token_with_wrong_signature(client: TestClient, db: Session) -> None:
    register(client)
    user = _user(db)
    forged = jwt.encode(
        {"sub": str(user.id), "ver": 0, "exp": clock.now() + timedelta(days=1)},
        "x" * 48,
        algorithm="HS256",
    )
    client.cookies.set(AUTH_COOKIE_NAME, forged)

    _assert_401(client.get(ME_URL), "UNAUTHENTICATED", cookie_cleared=True)


def test_broken_token(client: TestClient) -> None:
    client.cookies.set(AUTH_COOKIE_NAME, "not-a-jwt")

    _assert_401(client.get(ME_URL), "UNAUTHENTICATED", cookie_cleared=True)


def test_token_of_deleted_user(client: TestClient, db: Session) -> None:
    register(client)
    db.execute(delete(User))
    db.commit()

    _assert_401(client.get(ME_URL), "UNAUTHENTICATED", cookie_cleared=True)


def test_token_for_unknown_user_id(client: TestClient) -> None:
    token = create_access_token(uuid.uuid4(), 0, clock.now())
    client.cookies.set(AUTH_COOKIE_NAME, token)

    _assert_401(client.get(ME_URL), "UNAUTHENTICATED", cookie_cleared=True)


def test_unknown_url_uses_error_shape(client: TestClient) -> None:
    response = client.get("/api/v1/nothing-here")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
