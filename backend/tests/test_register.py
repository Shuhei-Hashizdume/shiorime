"""新規登録 POST /api/v1/auth/register（api.md 7-1）。"""

from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import AUTH_COOKIE_NAME, verify_password
from app.main import app
from app.models import RateLimitEvent, User
from tests.helpers import DEFAULT_PASSWORD, field_errors, register, register_body


def test_register_creates_user_and_logs_in(client: TestClient, db: Session) -> None:
    response = register(client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "taro@example.com"
    assert body["attribute"] == "working"
    assert set(body) == {"id", "email", "attribute"}

    # Cookie の属性（HttpOnly・Secure・SameSite=Lax・30日）
    set_cookie = response.headers["set-cookie"]
    assert set_cookie.startswith(f"{AUTH_COOKIE_NAME}=")
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Max-Age=2592000" in set_cookie

    # そのまま GET /me が通る＝ログイン状態になっている
    assert client.get("/api/v1/me").status_code == 200

    user = db.scalars(select(User)).one()
    assert user.password_hash != DEFAULT_PASSWORD
    assert verify_password(DEFAULT_PASSWORD, user.password_hash)
    assert user.terms_agreed_at is not None
    assert user.email_verified is False


def test_email_is_trimmed_and_lowercased(client: TestClient) -> None:
    response = register(client, email="  Taro@Example.COM ")

    assert response.status_code == 201
    assert response.json()["email"] == "taro@example.com"


def test_same_email_with_different_case_is_already_registered(client: TestClient) -> None:
    register(client)

    response = register(client, email="TARO@example.com")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


def test_password_surrounding_whitespace_is_removed(client: TestClient) -> None:
    register(client, password="  " + DEFAULT_PASSWORD + "  ")

    response = client.post(
        "/api/v1/auth/login", json={"email": "taro@example.com", "password": DEFAULT_PASSWORD}
    )

    assert response.status_code == 200


def test_password_length_boundaries(client: TestClient) -> None:
    assert register(client, email="a@example.com", password="a" * 7).status_code == 422
    assert register(client, email="b@example.com", password="a" * 8).status_code == 201
    assert register(client, email="c@example.com", password="a" * 128).status_code == 201
    response = register(client, email="d@example.com", password="a" * 129)

    assert response.status_code == 422
    assert field_errors(response) == [
        {"field": "password", "reason": "out_of_range", "min": 8, "max": 128}
    ]


def test_validation_error_shape(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "short", "attribute": "student", "agreed_to_terms": False},
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert sorted(field_errors(response), key=lambda f: f["field"]) == [
        {"field": "agreed_to_terms", "reason": "required"},
        {"field": "attribute", "reason": "invalid_value"},
        {"field": "email", "reason": "invalid_format"},
        {"field": "password", "reason": "out_of_range", "min": 8, "max": 128},
    ]


def test_missing_fields_are_required(client: TestClient) -> None:
    response = client.post("/api/v1/auth/register", json={})

    assert response.status_code == 422
    assert {f["field"]: f["reason"] for f in field_errors(response)} == {
        "email": "required",
        "password": "required",
        "attribute": "required",
        "agreed_to_terms": "required",
    }


def test_email_too_long(client: TestClient) -> None:
    email = "a" * 243 + "@example.com"  # 255文字
    response = register(client, email=email)

    assert response.status_code == 422
    assert field_errors(response) == [{"field": "email", "reason": "too_long", "limit": 254}]


def test_agreed_to_terms_must_be_true_boolean(client: TestClient) -> None:
    response = register(client, agreed_to_terms="true")

    assert response.status_code == 422
    assert field_errors(response)[0]["field"] == "agreed_to_terms"


def test_rate_limit_counts_success_and_duplicates_but_not_validation_errors(
    client: TestClient,
) -> None:
    # 入力の誤りは何回あっても数えない
    for _ in range(6):
        assert register(client, password="short").status_code == 422

    # 登録できた分と「既に登録されています」を合わせて5件まで
    assert register(client, email="u1@example.com").status_code == 201
    assert register(client, email="u2@example.com").status_code == 201
    assert register(client, email="u3@example.com").status_code == 201
    assert register(client, email="u1@example.com").status_code == 409
    assert register(client, email="u4@example.com").status_code == 201

    response = register(client, email="u5@example.com")

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "REGISTER_RATE_LIMIT"
    assert 1 <= int(response.headers["retry-after"]) <= 3600


def test_concurrent_registrations_with_same_email_create_one_user(db: Session) -> None:
    def send(i: int) -> int:
        with TestClient(app, base_url="https://testserver") as c:
            # 回数制限に当たらないよう、接続元を変える
            response = c.post(
                "/api/v1/auth/register",
                json=register_body(),
                headers={"X-Forwarded-For": f"203.0.113.{i}"},
            )
            return response.status_code

    with ThreadPoolExecutor(max_workers=5) as pool:
        statuses = list(pool.map(send, range(5)))

    assert sorted(statuses) == [201, 409, 409, 409, 409]
    assert db.scalar(select(func.count()).select_from(User)) == 1


def test_concurrent_registrations_do_not_exceed_rate_limit(db: Session) -> None:
    def send(i: int) -> int:
        with TestClient(app, base_url="https://testserver") as c:
            response = c.post(
                "/api/v1/auth/register", json=register_body(email=f"user{i}@example.com")
            )
            return response.status_code

    with ThreadPoolExecutor(max_workers=10) as pool:
        statuses = list(pool.map(send, range(10)))

    assert statuses.count(201) == 5
    assert statuses.count(429) == 5
    assert db.scalar(select(func.count()).select_from(RateLimitEvent)) == 5
