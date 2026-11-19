"""ログイン・ログアウト（api.md 7-1、5-2）。"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.security import AUTH_COOKIE_NAME
from app.main import app
from app.models import RateLimitEvent, RateLimitKind
from tests.helpers import DEFAULT_PASSWORD, register

LOGIN_URL = "/api/v1/auth/login"


def login(client: TestClient, email: str = "taro@example.com", password: str = DEFAULT_PASSWORD):
    return client.post(LOGIN_URL, json={"email": email, "password": password})


def _login_events(db: Session) -> int:
    return db.scalar(
        select(func.count()).select_from(RateLimitEvent).where(RateLimitEvent.kind == RateLimitKind.LOGIN)
    )


@pytest.fixture
def registered(client: TestClient) -> None:
    register(client)
    client.cookies.clear()


def test_login_succeeds(client: TestClient, registered: None) -> None:
    response = login(client)

    assert response.status_code == 200
    assert response.json()["email"] == "taro@example.com"
    assert set(response.json()) == {"id", "email", "attribute"}
    assert "HttpOnly" in response.headers["set-cookie"]
    assert client.get("/api/v1/me").status_code == 200


def test_login_email_is_case_insensitive(client: TestClient, registered: None) -> None:
    assert login(client, email="  TARO@example.com ").status_code == 200


def test_wrong_password_and_unknown_email_return_same_error(
    client: TestClient, registered: None
) -> None:
    wrong_password = login(client, password="wrong-password")
    unknown_email = login(client, email="nobody@example.com")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_unknown_email_still_computes_password_hash(client: TestClient) -> None:
    # 返事の速さで登録済みかを知られないよう、ダミーのハッシュで同じ計算をする
    with patch("app.services.auth.verify_dummy_password") as dummy:
        login(client, email="nobody@example.com")

    dummy.assert_called_once()


def test_empty_fields_are_validation_errors(client: TestClient) -> None:
    response = client.post(LOGIN_URL, json={"email": " ", "password": ""})

    assert response.status_code == 422
    assert {f["field"]: f["reason"] for f in response.json()["error"]["fields"]} == {
        "email": "required",
        "password": "required",
    }


def test_sixth_failure_is_rate_limited_before_checking_password(
    client: TestClient, registered: None
) -> None:
    for _ in range(5):
        assert login(client, password="wrong-password").status_code == 401

    # 6回目は、正しいパスワードでもパスワードを確かめる前に断る
    with patch("app.services.auth.verify_password") as verify:
        response = login(client)

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "LOGIN_RATE_LIMIT"
    assert 1 <= int(response.headers["retry-after"]) <= 60
    verify.assert_not_called()


def test_successful_logins_are_not_counted(client: TestClient, registered: None, db: Session) -> None:
    for _ in range(10):
        assert login(client).status_code == 200

    assert _login_events(db) == 0


def test_rate_limit_recovers_after_one_minute(client: TestClient, registered: None) -> None:
    for _ in range(5):
        login(client, password="wrong-password")
    assert login(client).status_code == 429

    later = clock.now() + timedelta(minutes=1, seconds=1)
    with patch("app.core.clock.now", return_value=later):
        assert login(client).status_code == 200


def test_rate_limit_is_per_client_ip(client: TestClient, registered: None) -> None:
    for _ in range(5):
        login(client, password="wrong-password")

    response = client.post(
        LOGIN_URL,
        json={"email": "taro@example.com", "password": DEFAULT_PASSWORD},
        headers={"X-Forwarded-For": "198.51.100.7"},
    )

    assert response.status_code == 200


def test_concurrent_failures_do_not_exceed_rate_limit(registered: None, db: Session) -> None:
    def send(_: int) -> int:
        with TestClient(app, base_url="https://testserver") as c:
            response = c.post(LOGIN_URL, json={"email": "taro@example.com", "password": "wrong-password"})
            return response.status_code

    with ThreadPoolExecutor(max_workers=10) as pool:
        statuses = list(pool.map(send, range(10)))

    assert statuses.count(401) == 5
    assert statuses.count(429) == 5
    assert _login_events(db) == 5


def test_logout_deletes_cookie(client: TestClient, registered: None) -> None:
    login(client)

    response = client.post("/api/v1/auth/logout")

    assert response.status_code == 204
    set_cookie = response.headers["set-cookie"]
    assert set_cookie.startswith(f'{AUTH_COOKIE_NAME}=""')
    assert "Max-Age=0" in set_cookie
    assert "HttpOnly" in set_cookie and "Secure" in set_cookie and "SameSite=lax" in set_cookie
    assert client.get("/api/v1/me").status_code == 401


def test_logout_without_login_is_still_204(client: TestClient) -> None:
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.post("/api/v1/auth/logout").status_code == 204


def test_logout_is_not_get(client: TestClient) -> None:
    response = client.get("/api/v1/auth/logout")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
