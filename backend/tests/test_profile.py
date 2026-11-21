"""プロフィール：属性の変更・パスワードの変更・退会（api.md 7-2）と、パスワードの再確認の回数制限（api.md 5-2）。"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core import clock
from app.core.security import AUTH_COOKIE_NAME
from app.main import app
from app.models import (
    AiProposal,
    AiUsage,
    AppAiUsage,
    Book,
    Insight,
    ProposalStatus,
    RateLimitEvent,
    RateLimitKind,
    User,
)
from tests.helpers import DEFAULT_PASSWORD, field_errors
from tests.test_insights import add_book, add_proposal, owner, write

ME = "/api/v1/me"
PASSWORD = "/api/v1/me/password"
WITHDRAW = "/api/v1/me/withdraw"
NEW_PASSWORD = "new-correct-horse"


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


def change(client: TestClient, current: str = DEFAULT_PASSWORD, new: str = NEW_PASSWORD):
    return client.post(PASSWORD, json={"current_password": current, "new_password": new})


def withdraw(client: TestClient, password: str = DEFAULT_PASSWORD):
    return client.post(WITHDRAW, json={"password": password})


def login(email: str, password: str) -> int:
    with TestClient(app, base_url="https://testserver") as c:
        return c.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
            headers={"X-Forwarded-For": "203.0.113.200"},
        ).status_code


def confirm_events(db: Session) -> int:
    return db.scalar(
        select(func.count()).select_from(RateLimitEvent).where(RateLimitEvent.kind == RateLimitKind.PASSWORD_CONFIRM)
    )


def assert_cookie_cleared(response) -> None:
    set_cookie = response.headers.get("set-cookie", "")
    assert set_cookie.startswith(f'{AUTH_COOKIE_NAME}=""')
    assert "Max-Age=0" in set_cookie


def same_device(client: TestClient) -> TestClient:
    """同じ JWT を持った別の端末"""
    c = TestClient(app, base_url="https://testserver", cookies=dict(client.cookies))
    c.__enter__()
    return c


# ---- 属性の変更 ----


def test_change_attribute(user_client: TestClient, db: Session) -> None:
    response = user_client.patch(ME, json={"attribute": "university"})

    assert response.status_code == 200
    body = response.json()
    assert body["attribute"] == "university"
    assert body["email"] == "reader@example.com"
    # GET /me と同じ形
    assert user_client.get(ME).json() == body


def test_change_attribute_validation(user_client: TestClient) -> None:
    for body in ({"attribute": "teacher"}, {}, {"attribute": "working", "email": "new@example.com"}):
        assert_error(user_client.patch(ME, json=body), 422, "VALIDATION_ERROR")
    assert user_client.get(ME).json()["attribute"] == "working"


def test_change_attribute_requires_login(client: TestClient) -> None:
    assert_error(client.patch(ME, json={"attribute": "other"}), 401, "UNAUTHENTICATED")


# ---- パスワードの変更 ----


def test_change_password_logs_out_everywhere(user_client: TestClient, db: Session) -> None:
    other_device = same_device(user_client)

    response = change(user_client, current=f"  {DEFAULT_PASSWORD} ", new=f" {NEW_PASSWORD} ")

    assert response.status_code == 204
    assert_cookie_cleared(response)
    # ほかの端末の JWT は使えなくなる
    assert_error(other_device.get(ME), 401, "TOKEN_REVOKED")
    other_device.__exit__(None, None, None)
    # 新しいパスワード（前後の空白は除く）でログインでき、古いパスワードではできない
    assert login("reader@example.com", NEW_PASSWORD) == 200
    assert login("reader@example.com", DEFAULT_PASSWORD) == 401
    assert db.scalar(select(User.token_version).where(User.email == "reader@example.com")) == 1


def test_wrong_current_password(user_client: TestClient, db: Session) -> None:
    response = change(user_client, current="wrong-password")

    # 401 にしない（画面が「ログインが切れた」と取り違えないため）
    assert_error(response, 400, "CURRENT_PASSWORD_INCORRECT")
    assert user_client.get(ME).status_code == 200
    assert confirm_events(db) == 1
    assert login("reader@example.com", DEFAULT_PASSWORD) == 200


def test_same_password_is_refused_and_not_counted(user_client: TestClient, db: Session) -> None:
    assert_error(change(user_client, new=f" {DEFAULT_PASSWORD} "), 400, "SAME_AS_CURRENT_PASSWORD")

    # 本人と確かめ済みなので数えない。ログインもそのまま
    assert confirm_events(db) == 0
    assert user_client.get(ME).status_code == 200


def test_change_password_validation(user_client: TestClient, db: Session) -> None:
    response = change(user_client, new="short")

    assert_error(response, 422, "VALIDATION_ERROR")
    assert field_errors(response) == [{"field": "new_password", "reason": "out_of_range", "min": 8, "max": 128}]
    assert_error(change(user_client, current="   "), 422, "VALIDATION_ERROR")
    assert_error(user_client.post(PASSWORD, json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD, "x": 1}), 422, "VALIDATION_ERROR")
    # 入力の誤りは数えない
    assert confirm_events(db) == 0


def test_change_password_requires_login(client: TestClient) -> None:
    assert_error(change(client), 401, "UNAUTHENTICATED")


# ---- 退会 ----


def test_withdraw_deletes_all_my_data(
    user_client: TestClient, other_client: TestClient, db: Session
) -> None:
    me = owner(db)
    insight_id = write(user_client, add_book(user_client))
    add_proposal(db, insight_id, me, ProposalStatus.COMPLETED)
    today = clock.jst_date(clock.now())
    db.add_all([AiUsage(user_id=me, usage_date=today, used_count=2), AppAiUsage(usage_date=today, used_count=7)])
    db.commit()
    others_insight = write(other_client, add_book(other_client, title="ほかの人の本"))
    other_device = same_device(user_client)

    response = withdraw(user_client, f" {DEFAULT_PASSWORD} ")

    assert response.status_code == 204
    assert_cookie_cleared(response)
    assert db.scalar(select(func.count()).select_from(User).where(User.id == me)) == 0
    for model in (Book, Insight, AiProposal, AiUsage):
        assert db.scalar(select(func.count()).select_from(model).where(model.user_id == me)) == 0
    # アプリ全体の回数は減らない
    assert db.scalar(select(AppAiUsage.used_count).where(AppAiUsage.usage_date == today)) == 7
    # ほかの人のデータは残る
    assert db.get(Insight, uuid.UUID(others_insight)) is not None
    # ほかの端末の JWT は、ユーザーがいないので断られる
    assert_error(other_device.get(ME), 401, "UNAUTHENTICATED")
    other_device.__exit__(None, None, None)
    assert login("reader@example.com", DEFAULT_PASSWORD) == 401


def test_withdraw_with_wrong_password(user_client: TestClient, db: Session) -> None:
    assert_error(withdraw(user_client, "wrong-password"), 400, "PASSWORD_INCORRECT")

    assert user_client.get(ME).status_code == 200
    assert confirm_events(db) == 1


def test_withdraw_validation(user_client: TestClient, db: Session) -> None:
    response = withdraw(user_client, "  ")

    assert_error(response, 422, "VALIDATION_ERROR")
    assert field_errors(response) == [{"field": "password", "reason": "required"}]
    assert user_client.get(ME).status_code == 200


def test_withdraw_requires_login(client: TestClient) -> None:
    assert_error(withdraw(client), 401, "UNAUTHENTICATED")


def test_withdraw_while_proposal_is_generating(user_client: TestClient, db: Session) -> None:
    insight_id = write(user_client, add_book(user_client))
    add_proposal(db, insight_id, owner(db), ProposalStatus.GENERATING_PLANS, question="質問", answer="回答")

    assert withdraw(user_client).status_code == 204
    assert db.scalar(select(func.count()).select_from(AiProposal)) == 0


# ---- パスワードの再確認の回数制限（api.md 5-2） ----


def test_sixth_failure_is_refused_even_with_correct_password(user_client: TestClient, db: Session) -> None:
    # 変更と退会を合わせて数える
    for i in range(5):
        response = change(user_client, current="wrong") if i % 2 else withdraw(user_client, "wrong")
        assert response.status_code == 400

    # 上限に達したら、パスワードを確かめる前に断る（正しいパスワードでも）
    with patch("app.services.me.verify_password") as verify:
        response = change(user_client)
        assert verify.call_count == 0
    assert_error(response, 429, "PASSWORD_CONFIRM_RATE_LIMIT")
    assert 1 <= int(response.headers["retry-after"]) <= 3600
    assert_error(withdraw(user_client), 429, "PASSWORD_CONFIRM_RATE_LIMIT")
    # 全端末からはログアウトさせない
    assert user_client.get(ME).status_code == 200


def test_rate_limit_recovers_after_one_hour(user_client: TestClient, db: Session) -> None:
    for _ in range(5):
        change(user_client, current="wrong")
    db.execute(update(RateLimitEvent).values(occurred_at=clock.now() - timedelta(hours=1, seconds=1)))
    db.commit()

    assert change(user_client).status_code == 204


def test_rate_limit_is_per_user(user_client: TestClient, other_client: TestClient) -> None:
    for _ in range(5):
        change(user_client, current="wrong")

    assert change(other_client).status_code == 204


def test_successes_are_not_counted(user_client: TestClient, db: Session) -> None:
    assert change(user_client).status_code == 204

    assert confirm_events(db) == 0


def test_concurrent_failures_do_not_exceed_rate_limit(user_client: TestClient, db: Session) -> None:
    cookies = dict(user_client.cookies)

    def send(_: int) -> int:
        with TestClient(app, base_url="https://testserver", cookies=cookies) as c:
            return change(c, current="wrong").status_code

    with ThreadPoolExecutor(max_workers=10) as pool:
        statuses = list(pool.map(send, range(10)))

    assert statuses.count(400) == 5
    assert statuses.count(429) == 5
    assert confirm_events(db) == 5
