"""AI提案（api.md 2章・7-6）と、本日の残り回数（api.md 7-2 `GET /me/ai-usage`）。

AI は偽物（tests/fakes.py の FakeAi）に置き換える。裏の処理（BackgroundTasks）は、
TestClient では返事が返る前に終わるので、呼んだ直後に結果を確かめられる。
"""

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core import clock
from app.db import SessionLocal
from app.jobs.cleanup import run_cleanup
from app.main import app
from app.models import AiProposal, AiUsage, AppAiUsage, Insight, ProposalStatus, RateLimitEvent
from app.services import ai_proposals
from app.services.ai_client import AiError
from tests.fakes import PLANS, QUESTION, FakeAi
from tests.test_insights import add_book, add_proposal, owner, write

S = ProposalStatus
INSIGHTS = "/api/v1/insights"
PROPOSALS = "/api/v1/ai-proposals"
USAGE = "/api/v1/me/ai-usage"


# ---- 準備 ----


def new_insight(client: TestClient) -> str:
    book_id = add_book(client)
    return write(client, book_id, body="上司の機嫌を自分の責任だと思い込んでいた", quote="他者の課題には踏み込まない", page=142)


def start(client: TestClient, insight_id: str, key: uuid.UUID | None = None):
    return client.post(
        f"{INSIGHTS}/{insight_id}/ai-proposals", headers={"Idempotency-Key": str(key or uuid.uuid4())}
    )


def started(client: TestClient, insight_id: str) -> str:
    response = start(client, insight_id)
    assert response.status_code == 202, response.text
    return response.json()["id"]


def get(client: TestClient, proposal_id: str) -> dict:
    response = client.get(f"{PROPOSALS}/{proposal_id}")
    assert response.status_code == 200, response.text
    return response.json()


def send_answer(client: TestClient, proposal_id: str, answer: str = "無能だと思われたくない焦りだと思う"):
    return client.post(f"{PROPOSALS}/{proposal_id}/answer", json={"answer": answer})


def send_retry(client: TestClient, proposal_id: str, answer: str = "無能だと思われたくない焦りだと思う"):
    return client.post(f"{PROPOSALS}/{proposal_id}/retry", json={"answer": answer})


def today() -> date:
    return clock.jst_date(clock.now())


def personal_used(db: Session, user_id: uuid.UUID, on: date | None = None) -> int:
    return db.scalar(
        select(AiUsage.used_count).where(AiUsage.user_id == user_id, AiUsage.usage_date == (on or today()))
    ) or 0


def app_used(db: Session, on: date | None = None) -> int:
    return db.scalar(select(AppAiUsage.used_count).where(AppAiUsage.usage_date == (on or today()))) or 0


def set_usage(db: Session, user_id: uuid.UUID, personal: int, app_count: int = 0) -> None:
    db.add(AiUsage(user_id=user_id, usage_date=today(), used_count=personal))
    if app_count:
        db.add(AppAiUsage(usage_date=today(), used_count=app_count))
    db.commit()


def proposal_row(db: Session, proposal_id: str | uuid.UUID) -> AiProposal | None:
    db.expire_all()
    return db.get(AiProposal, uuid.UUID(str(proposal_id)))


def proposal_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(AiProposal))


def make_old(db: Session, proposal_id: str | uuid.UUID, ago: timedelta) -> None:
    """状態が変わってから ago だけたった形にする（2分・24時間の判定を確かめるため）"""
    db.execute(
        update(AiProposal)
        .where(AiProposal.id == uuid.UUID(str(proposal_id)))
        .values(status_changed_at=clock.now() - ago)
    )
    db.commit()


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


def other_cookies(client: TestClient) -> dict[str, str]:
    return dict(client.cookies)


def in_threads(count: int, send) -> list[int]:
    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(send, range(count)))


# ---- 始める ----


def test_start_creates_proposal_and_question(user_client: TestClient, ai: FakeAi, db: Session) -> None:
    insight_id = new_insight(user_client)

    response = start(user_client, insight_id)

    assert response.status_code == 202
    proposal_id = response.json()["id"]
    assert response.headers["location"] == f"/api/v1/ai-proposals/{proposal_id}"
    body = get(user_client, proposal_id)
    assert body == {
        "id": proposal_id,
        "status": "awaiting_answer",
        "insight_id": insight_id,
        "insight": {
            "book_title": "嫌われる勇気",
            "page": 142,
            "quote": "他者の課題には踏み込まない",
            "body": "上司の機嫌を自分の責任だと思い込んでいた",
        },
        "question": QUESTION,
        "answer": None,
        "plans": None,
        "completed_at": None,
        "retries_left": 3,
    }
    assert personal_used(db, owner(db)) == 1
    assert app_used(db) == 1


def test_start_sends_only_allowed_information_to_ai(user_client: TestClient, ai: FakeAi) -> None:
    started(user_client, new_insight(user_client))

    # 要件定義書 7.1：属性（日本語に直す）・本・引用・気づきだけを送る。ページ番号やアカウントの情報は送らない
    (context,) = ai.question_calls
    assert context.attribute == "社会人"
    assert context.book_title == "嫌われる勇気"
    assert context.book_author == "岸見一郎"
    assert context.quote == "他者の課題には踏み込まない"
    assert context.body == "上司の機嫌を自分の責任だと思い込んでいた"
    assert not hasattr(context, "page")


def test_start_requires_idempotency_key(user_client: TestClient, ai: FakeAi, db: Session) -> None:
    insight_id = new_insight(user_client)

    response = user_client.post(f"{INSIGHTS}/{insight_id}/ai-proposals")

    assert_error(response, 422, "VALIDATION_ERROR")
    assert proposal_count(db) == 0


def test_start_requires_login(client: TestClient, ai: FakeAi) -> None:
    assert_error(start(client, str(uuid.uuid4())), 401, "UNAUTHENTICATED")


def test_start_on_other_users_insight_is_not_found(
    user_client: TestClient, other_client: TestClient, ai: FakeAi, db: Session
) -> None:
    insight_id = new_insight(user_client)

    assert_error(start(other_client, insight_id), 404, "INSIGHT_NOT_FOUND")
    assert_error(start(user_client, str(uuid.uuid4())), 404, "INSIGHT_NOT_FOUND")
    assert proposal_count(db) == 0
    assert personal_used(db, owner(db, "other@example.com")) == 0
    assert app_used(db) == 0


def test_same_idempotency_key_returns_same_proposal(user_client: TestClient, ai: FakeAi, db: Session) -> None:
    insight_id = new_insight(user_client)
    key = uuid.uuid4()

    first = start(user_client, insight_id, key)
    second = start(user_client, insight_id, key)

    # 2回目も1回目とまったく同じ返事（api.md 7-6）
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert first.headers["location"] == second.headers["location"]
    assert proposal_count(db) == 1
    assert personal_used(db, owner(db)) == 1
    assert len(ai.question_calls) == 1


def test_concurrent_same_idempotency_key_creates_one_proposal(
    user_client: TestClient, ai: FakeAi, db: Session
) -> None:
    insight_id = new_insight(user_client)
    key = uuid.uuid4()
    cookies = other_cookies(user_client)
    ids: list[str] = []

    def send(_: int) -> int:
        with TestClient(app, base_url="https://testserver", cookies=cookies) as c:
            response = start(c, insight_id, key)
            ids.append(response.json().get("id", ""))
            return response.status_code

    statuses = in_threads(5, send)

    assert statuses == [202] * 5
    assert len(set(ids)) == 1
    assert proposal_count(db) == 1
    assert personal_used(db, owner(db)) == 1
    assert app_used(db) == 1
    assert len(ai.question_calls) == 1


def test_same_key_after_question_failed_returns_failed_proposal(
    user_client: TestClient, ai: FakeAi, db: Session
) -> None:
    insight_id = new_insight(user_client)
    key = uuid.uuid4()
    ai.questions = [AiError("refusal", retryable=False)]
    first = start(user_client, insight_id, key)

    second = start(user_client, insight_id, key)

    # 失敗した方を返し、新しく作らない（回数は失敗したときに戻し済みなので、二重には使わない）
    assert second.status_code == 202
    assert second.json() == first.json()
    assert get(user_client, first.json()["id"])["status"] == "question_failed"
    assert proposal_count(db) == 1
    assert personal_used(db, owner(db)) == 0
    assert len(ai.question_calls) == 1


def test_start_while_processing_is_refused(user_client: TestClient, ai: FakeAi, db: Session) -> None:
    insight_id = new_insight(user_client)
    me = owner(db)
    for status in (S.GENERATING_QUESTION, S.GENERATING_PLANS):
        proposal_id = add_proposal(db, insight_id, me, status, usage_date=today(), answer="回答")

        assert_error(start(user_client, insight_id), 409, "AI_PROPOSAL_IN_PROGRESS")
        assert personal_used(db, me) == 0
        assert proposal_row(db, proposal_id) is not None
        db.delete(proposal_row(db, proposal_id))
        db.commit()


def test_concurrent_starts_on_same_insight_use_one_count(
    user_client: TestClient, ai: FakeAi, db: Session
) -> None:
    insight_id = new_insight(user_client)
    cookies = other_cookies(user_client)
    # 1つ目の深掘りを作っている間は「処理中」のままにしておく
    ai.gate = threading.Event()

    def send(_: int) -> int:
        with TestClient(app, base_url="https://testserver", cookies=cookies) as c:
            return start(c, insight_id).status_code

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(send, i) for i in range(5)]
        deadline = time.monotonic() + 10
        while sum(f.done() for f in futures) < 4 and time.monotonic() < deadline:
            time.sleep(0.02)
        ai.gate.set()
        statuses = [f.result() for f in futures]

    assert sorted(statuses) == [202, 409, 409, 409, 409]
    assert proposal_count(db) == 1
    assert personal_used(db, owner(db)) == 1
    assert len(ai.question_calls) == 1


def test_start_removes_unfinished_proposals_but_keeps_completed(
    user_client: TestClient, ai: FakeAi, db: Session
) -> None:
    insight_id = new_insight(user_client)
    me = owner(db)
    completed = add_proposal(db, insight_id, me, S.COMPLETED)
    leftovers = [
        add_proposal(db, insight_id, me, S.AWAITING_ANSWER, question="質問"),
        add_proposal(db, insight_id, me, S.QUESTION_FAILED),
        add_proposal(db, insight_id, me, S.RETRY_LIMIT_REACHED, question="質問", answer="回答", retry_count=3),
    ]

    new_id = started(user_client, insight_id)

    assert all(proposal_row(db, p) is None for p in leftovers)
    # 完了したものは、新しいものが完了するまで残す
    assert proposal_row(db, completed) is not None
    assert proposal_row(db, new_id) is not None


# ---- 回数の上限 ----


def test_start_refused_when_daily_limit_used(user_client: TestClient, ai: FakeAi, db: Session) -> None:
    insight_id = new_insight(user_client)
    me = owner(db)
    set_usage(db, me, personal=5, app_count=5)

    assert_error(start(user_client, insight_id), 429, "AI_DAILY_LIMIT")
    assert personal_used(db, me) == 5
    assert app_used(db) == 5
    assert proposal_count(db) == 0
    assert ai.question_calls == []


def test_start_refused_when_app_limit_reached(user_client: TestClient, ai: FakeAi, db: Session) -> None:
    insight_id = new_insight(user_client)
    me = owner(db)
    set_usage(db, me, personal=2, app_count=100)

    assert_error(start(user_client, insight_id), 429, "AI_APP_LIMIT")
    # 個人の +1 も一緒に取り消す
    assert personal_used(db, me) == 2
    assert app_used(db) == 100
    assert proposal_count(db) == 0


def test_concurrent_starts_do_not_exceed_daily_limit(user_client: TestClient, ai: FakeAi, db: Session) -> None:
    insight_ids = [new_insight(user_client) for _ in range(8)]
    cookies = other_cookies(user_client)

    def send(i: int) -> int:
        with TestClient(app, base_url="https://testserver", cookies=cookies) as c:
            return start(c, insight_ids[i]).status_code

    statuses = in_threads(8, send)

    assert statuses.count(202) == 5
    assert statuses.count(429) == 3
    assert personal_used(db, owner(db)) == 5
    assert app_used(db) == 5
    assert proposal_count(db) == 5


def test_day_changes_at_midnight_in_japan(
    user_client: TestClient, ai: FakeAi, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    insight_id = new_insight(user_client)
    me = owner(db)
    # 日本時間 2026-11-20 は使い切っている
    db.add(AiUsage(user_id=me, usage_date=date(2026, 11, 20), used_count=5))
    db.commit()

    # 日本時間 23:59:59（UTC 14:59:59）はまだ同じ日
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 20, 14, 59, 59, tzinfo=UTC))
    assert_error(start(user_client, insight_id), 429, "AI_DAILY_LIMIT")

    # 日本時間 0:00（UTC 15:00）で次の日になり、また使える
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 20, 15, 0, tzinfo=UTC))
    proposal_id = started(user_client, insight_id)
    assert proposal_row(db, proposal_id).usage_date == date(2026, 11, 21)
    assert personal_used(db, me, date(2026, 11, 21)) == 1
    assert personal_used(db, me, date(2026, 11, 20)) == 5


# ---- 深掘りの作成 ----


def test_question_failure_returns_counts(user_client: TestClient, ai: FakeAi, db: Session) -> None:
    ai.questions = [AiError("refusal", retryable=False)]

    proposal_id = started(user_client, new_insight(user_client))

    body = get(user_client, proposal_id)
    assert body["status"] == "question_failed"
    assert body["question"] is None
    # 深掘りの作成に失敗したら、個人とアプリ全体の回数を戻す
    assert personal_used(db, owner(db)) == 0
    assert app_used(db) == 0


def test_temporary_question_failure_is_retried_once(user_client: TestClient, ai: FakeAi) -> None:
    ai.questions = [AiError("server_error", retryable=True), "やり直した質問"]

    proposal_id = started(user_client, new_insight(user_client))

    assert len(ai.question_calls) == 2
    assert get(user_client, proposal_id)["question"] == "やり直した質問"


def test_question_fails_after_two_temporary_failures(user_client: TestClient, ai: FakeAi) -> None:
    ai.questions = [AiError("server_error", retryable=True), AiError("server_error", retryable=True), "3回目"]

    proposal_id = started(user_client, new_insight(user_client))

    # AI の呼び出しは最大2回
    assert len(ai.question_calls) == 2
    assert get(user_client, proposal_id)["status"] == "question_failed"


def test_permanent_question_failure_is_not_retried(user_client: TestClient, ai: FakeAi) -> None:
    ai.questions = [AiError("insufficient_quota", retryable=False), "呼ばれないはず"]

    proposal_id = started(user_client, new_insight(user_client))

    assert len(ai.question_calls) == 1
    assert get(user_client, proposal_id)["status"] == "question_failed"


def test_question_is_discarded_if_proposal_ended_meanwhile(
    user_client: TestClient, ai: FakeAi, db: Session
) -> None:
    insight_id = new_insight(user_client)

    def end_meanwhile() -> None:
        # 深掘りを作っている間に、別の画面で終了させた（行がなくなった）
        with SessionLocal() as other:
            other.query(AiProposal).delete()
            other.commit()

    ai.before_question_returns = end_meanwhile

    proposal_id = started(user_client, insight_id)

    assert_error(user_client.get(f"{PROPOSALS}/{proposal_id}"), 404, "AI_PROPOSAL_NOT_FOUND")
    assert proposal_count(db) == 0
    # 回答前に終わったので、回数は戻らない
    assert personal_used(db, owner(db)) == 1


# ---- 取得 ----


def test_get_other_users_proposal_is_not_found(
    user_client: TestClient, other_client: TestClient, ai: FakeAi
) -> None:
    proposal_id = started(user_client, new_insight(user_client))

    assert_error(other_client.get(f"{PROPOSALS}/{proposal_id}"), 404, "AI_PROPOSAL_NOT_FOUND")
    assert_error(user_client.get(f"{PROPOSALS}/{uuid.uuid4()}"), 404, "AI_PROPOSAL_NOT_FOUND")


def test_get_shows_insight_as_it_was_when_started(user_client: TestClient, ai: FakeAi, db: Session) -> None:
    insight_id = new_insight(user_client)
    proposal_id = started(user_client, insight_id)

    response = user_client.patch(f"{INSIGHTS}/{insight_id}", json={"body": "書き直した本文", "quote": "", "page": 10})
    assert response.status_code == 204

    insight = get(user_client, proposal_id)["insight"]
    # 引用・本文は始めた時点の写し。ページは元の気づきから取る
    assert insight["body"] == "上司の機嫌を自分の責任だと思い込んでいた"
    assert insight["quote"] == "他者の課題には踏み込まない"
    assert insight["page"] == 10


# ---- 回答を送る ----


def test_answer_completes_with_plans(user_client: TestClient, ai: FakeAi, db: Session) -> None:
    proposal_id = started(user_client, new_insight(user_client))

    response = send_answer(user_client, proposal_id, "  無能だと思われたくない焦り  ")

    assert response.status_code == 202
    assert response.content == b""
    assert "location" not in response.headers
    body = get(user_client, proposal_id)
    assert body["status"] == "completed"
    assert body["answer"] == "無能だと思われたくない焦り"
    assert body["plans"] == [{"text": text} for text in PLANS]
    assert body["completed_at"] is not None
    (_, question, answer), = ai.plan_calls
    assert question == QUESTION
    assert answer == "無能だと思われたくない焦り"
    assert personal_used(db, owner(db)) == 1


@pytest.mark.parametrize(
    "body",
    [
        {"answer": ""},
        {"answer": "   "},
        {"answer": "あ" * 501},
        {},
        {"answer": "回答", "extra": 1},
    ],
)
def test_answer_validation(user_client: TestClient, ai: FakeAi, body: dict) -> None:
    proposal_id = started(user_client, new_insight(user_client))

    response = user_client.post(f"{PROPOSALS}/{proposal_id}/answer", json=body)

    assert_error(response, 422, "VALIDATION_ERROR")
    assert get(user_client, proposal_id)["status"] == "awaiting_answer"


def test_answer_counts_visible_characters(user_client: TestClient, ai: FakeAi) -> None:
    proposal_id = started(user_client, new_insight(user_client))

    # 肌の色つきの絵文字は、中身は2つでも見た目で1文字。500個なら受け付け、501個なら断る
    assert send_answer(user_client, proposal_id, "👍🏽" * 501).status_code == 422
    assert send_answer(user_client, proposal_id, "👍🏽" * 500).status_code == 202


def test_answer_twice_is_conflict(user_client: TestClient, ai: FakeAi) -> None:
    proposal_id = started(user_client, new_insight(user_client))
    assert send_answer(user_client, proposal_id).status_code == 202

    assert_error(send_answer(user_client, proposal_id), 409, "AI_PROPOSAL_STATE_CONFLICT")
    assert len(ai.plan_calls) == 1


def test_concurrent_answers_call_ai_once(user_client: TestClient, ai: FakeAi) -> None:
    proposal_id = started(user_client, new_insight(user_client))
    cookies = other_cookies(user_client)

    def send(_: int) -> int:
        with TestClient(app, base_url="https://testserver", cookies=cookies) as c:
            return send_answer(c, proposal_id).status_code

    statuses = in_threads(5, send)

    assert sorted(statuses) == [202, 409, 409, 409, 409]
    assert len(ai.plan_calls) == 1


def test_answer_while_generating_question_is_conflict(user_client: TestClient, ai: FakeAi, db: Session) -> None:
    insight_id = new_insight(user_client)
    proposal_id = add_proposal(db, insight_id, owner(db), S.GENERATING_QUESTION)

    assert_error(send_answer(user_client, str(proposal_id)), 409, "AI_PROPOSAL_STATE_CONFLICT")


def test_answer_other_users_proposal_is_not_found(
    user_client: TestClient, other_client: TestClient, ai: FakeAi
) -> None:
    proposal_id = started(user_client, new_insight(user_client))

    assert_error(send_answer(other_client, proposal_id), 404, "AI_PROPOSAL_NOT_FOUND")
    assert_error(send_answer(user_client, str(uuid.uuid4())), 404, "AI_PROPOSAL_NOT_FOUND")
    assert get(user_client, proposal_id)["status"] == "awaiting_answer"


def test_answer_after_24_hours_is_not_found(user_client: TestClient, ai: FakeAi, db: Session) -> None:
    proposal_id = started(user_client, new_insight(user_client))
    make_old(db, proposal_id, timedelta(hours=24, minutes=1))

    assert_error(send_answer(user_client, proposal_id), 404, "AI_PROPOSAL_NOT_FOUND")
    assert proposal_row(db, proposal_id) is None
    assert ai.plan_calls == []


def test_answer_just_before_24_hours_is_accepted(user_client: TestClient, ai: FakeAi, db: Session) -> None:
    proposal_id = started(user_client, new_insight(user_client))
    make_old(db, proposal_id, timedelta(hours=23, minutes=59))

    assert send_answer(user_client, proposal_id).status_code == 202


def test_completion_replaces_previous_completed(user_client: TestClient, ai: FakeAi, db: Session) -> None:
    insight_id = new_insight(user_client)
    old = add_proposal(db, insight_id, owner(db), S.COMPLETED)
    proposal_id = started(user_client, insight_id)

    send_answer(user_client, proposal_id)

    assert proposal_row(db, old) is None
    completed = db.scalars(
        select(AiProposal.id).where(AiProposal.insight_id == uuid.UUID(insight_id), AiProposal.status == S.COMPLETED)
    ).all()
    assert [str(p) for p in completed] == [proposal_id]


# ---- 行動プランの失敗と送り直し ----


def test_plan_failure_can_be_retried(user_client: TestClient, ai: FakeAi, db: Session) -> None:
    proposal_id = started(user_client, new_insight(user_client))
    ai.plans = [AiError("refusal", retryable=False)]
    send_answer(user_client, proposal_id, "最初の回答")

    failed = get(user_client, proposal_id)
    assert failed["status"] == "plan_failed"
    assert failed["answer"] == "最初の回答"
    assert failed["retries_left"] == 3

    # 回答を書き直して送り直す。1日の回数は使わない
    assert send_retry(user_client, proposal_id, "書き直した回答").status_code == 202

    body = get(user_client, proposal_id)
    assert body["status"] == "completed"
    assert body["answer"] == "書き直した回答"
    assert body["retries_left"] == 2
    assert ai.plan_calls[-1][2] == "書き直した回答"
    assert personal_used(db, owner(db)) == 1
    assert app_used(db) == 1


def test_temporary_plan_failure_is_retried_once(user_client: TestClient, ai: FakeAi) -> None:
    proposal_id = started(user_client, new_insight(user_client))
    ai.plans = [AiError("timeout", retryable=True), PLANS]

    send_answer(user_client, proposal_id)

    assert len(ai.plan_calls) == 2
    assert get(user_client, proposal_id)["status"] == "completed"


def test_retry_limit_ends_proposal_and_returns_personal_count(
    user_client: TestClient, ai: FakeAi, db: Session
) -> None:
    proposal_id = started(user_client, new_insight(user_client))
    ai.plans = [AiError("refusal", retryable=False)] * 4

    send_answer(user_client, proposal_id)
    for left in (2, 1, 0):
        assert send_retry(user_client, proposal_id).status_code == 202
        if left:
            assert get(user_client, proposal_id)["retries_left"] == left

    body = get(user_client, proposal_id)
    assert body["status"] == "retry_limit_reached"
    assert body["answer"] is not None
    assert body["plans"] is None
    assert len(ai.plan_calls) == 4
    # 本人の回数は戻し、アプリ全体は戻さない
    assert personal_used(db, owner(db)) == 0
    assert app_used(db) == 1
    assert_error(send_retry(user_client, proposal_id), 409, "AI_PROPOSAL_STATE_CONFLICT")


@pytest.mark.parametrize("status", [S.AWAITING_ANSWER, S.GENERATING_PLANS, S.COMPLETED, S.QUESTION_FAILED])
def test_retry_in_wrong_state_is_conflict(
    user_client: TestClient, ai: FakeAi, db: Session, status: ProposalStatus
) -> None:
    # 回答待ち（まだ回答していない）・作成中・完了・失敗して終わったものは、送り直せない
    insight_id = new_insight(user_client)
    answer = None if status in (S.AWAITING_ANSWER, S.QUESTION_FAILED) else "回答"
    proposal_id = add_proposal(db, insight_id, owner(db), status, question="質問", answer=answer)

    assert_error(send_retry(user_client, str(proposal_id)), 409, "AI_PROPOSAL_STATE_CONFLICT")
    assert proposal_row(db, proposal_id).retry_count == 0
    assert ai.plan_calls == []


def test_retry_other_users_proposal_is_not_found(
    user_client: TestClient, other_client: TestClient, ai: FakeAi, db: Session
) -> None:
    insight_id = new_insight(user_client)
    proposal_id = add_proposal(db, insight_id, owner(db), S.AWAITING_ANSWER, question="質問", answer="回答")

    assert_error(send_retry(other_client, str(proposal_id)), 404, "AI_PROPOSAL_NOT_FOUND")
    assert proposal_row(db, proposal_id).retry_count == 0


def test_concurrent_retries_count_once(user_client: TestClient, ai: FakeAi, db: Session) -> None:
    insight_id = new_insight(user_client)
    proposal_id = add_proposal(db, insight_id, owner(db), S.AWAITING_ANSWER, question="質問", answer="回答")
    cookies = other_cookies(user_client)

    def send(_: int) -> int:
        with TestClient(app, base_url="https://testserver", cookies=cookies) as c:
            return send_retry(c, str(proposal_id)).status_code

    statuses = in_threads(5, send)

    assert sorted(statuses) == [202, 409, 409, 409, 409]
    assert proposal_row(db, proposal_id).retry_count == 1
    assert len(ai.plan_calls) == 1


# ---- 途中でやめる ----


@pytest.mark.parametrize(
    ("status", "answer"),
    [(S.GENERATING_QUESTION, None), (S.AWAITING_ANSWER, None), (S.AWAITING_ANSWER, "回答")],
    ids=["generating_question", "awaiting_answer", "plan_failed"],
)
def test_abandon_before_answer(
    user_client: TestClient, ai: FakeAi, db: Session, status: ProposalStatus, answer: str | None
) -> None:
    insight_id = new_insight(user_client)
    me = owner(db)
    set_usage(db, me, personal=1, app_count=1)
    proposal_id = add_proposal(db, insight_id, me, status, question="質問", answer=answer, usage_date=today())

    response = user_client.post(f"{PROPOSALS}/{proposal_id}/abandon")

    assert response.status_code == 204
    assert proposal_row(db, proposal_id) is None
    # 回数は戻さない
    assert personal_used(db, me) == 1
    assert app_used(db) == 1


@pytest.mark.parametrize("status", [S.GENERATING_PLANS, S.COMPLETED, S.QUESTION_FAILED, S.RETRY_LIMIT_REACHED])
def test_abandon_after_answer_is_conflict(
    user_client: TestClient, ai: FakeAi, db: Session, status: ProposalStatus
) -> None:
    insight_id = new_insight(user_client)
    proposal_id = add_proposal(db, insight_id, owner(db), status, question="質問", answer="回答")

    assert_error(user_client.post(f"{PROPOSALS}/{proposal_id}/abandon"), 409, "AI_PROPOSAL_STATE_CONFLICT")
    assert proposal_row(db, proposal_id) is not None


def test_abandon_other_users_proposal_is_not_found(
    user_client: TestClient, other_client: TestClient, ai: FakeAi, db: Session
) -> None:
    proposal_id = started(user_client, new_insight(user_client))

    assert_error(other_client.post(f"{PROPOSALS}/{proposal_id}/abandon"), 404, "AI_PROPOSAL_NOT_FOUND")
    assert proposal_row(db, proposal_id) is not None


# ---- 止まったAI提案の片付け（api.md 2-8） ----


def test_question_stuck_over_2_minutes_fails_and_returns_counts(
    user_client: TestClient, ai: FakeAi, db: Session
) -> None:
    insight_id = new_insight(user_client)
    me = owner(db)
    set_usage(db, me, personal=1, app_count=1)
    proposal_id = add_proposal(db, insight_id, me, S.GENERATING_QUESTION, usage_date=today())

    make_old(db, proposal_id, timedelta(seconds=110))
    assert get(user_client, str(proposal_id))["status"] == "generating_question"
    assert personal_used(db, me) == 1

    make_old(db, proposal_id, timedelta(seconds=130))
    assert get(user_client, str(proposal_id))["status"] == "question_failed"
    assert personal_used(db, me) == 0
    assert app_used(db) == 0


def test_plans_stuck_over_2_minutes_can_be_retried(user_client: TestClient, ai: FakeAi, db: Session) -> None:
    insight_id = new_insight(user_client)
    proposal_id = add_proposal(
        db, insight_id, owner(db), S.GENERATING_PLANS, question="質問", answer="回答", retry_count=1
    )
    make_old(db, proposal_id, timedelta(minutes=3))

    body = get(user_client, str(proposal_id))

    assert body["status"] == "plan_failed"
    assert body["retries_left"] == 2


def test_fourth_send_stuck_ends_proposal_and_returns_personal_count(
    user_client: TestClient, ai: FakeAi, db: Session
) -> None:
    insight_id = new_insight(user_client)
    me = owner(db)
    set_usage(db, me, personal=1, app_count=1)
    proposal_id = add_proposal(
        db, insight_id, me, S.GENERATING_PLANS, question="質問", answer="回答", retry_count=3, usage_date=today()
    )
    make_old(db, proposal_id, timedelta(minutes=3))

    assert get(user_client, str(proposal_id))["status"] == "retry_limit_reached"
    assert personal_used(db, me) == 0
    assert app_used(db) == 1


@pytest.mark.parametrize(
    ("status", "answer"),
    [(S.AWAITING_ANSWER, None), (S.AWAITING_ANSWER, "回答"), (S.QUESTION_FAILED, None), (S.RETRY_LIMIT_REACHED, "回答")],
    ids=["awaiting_answer", "plan_failed", "question_failed", "retry_limit_reached"],
)
def test_unfinished_proposals_are_deleted_after_24_hours(
    user_client: TestClient, ai: FakeAi, db: Session, status: ProposalStatus, answer: str | None
) -> None:
    insight_id = new_insight(user_client)
    proposal_id = add_proposal(db, insight_id, owner(db), status, question="質問", answer=answer)

    make_old(db, proposal_id, timedelta(hours=23, minutes=59))
    assert user_client.get(f"{PROPOSALS}/{proposal_id}").status_code == 200

    make_old(db, proposal_id, timedelta(hours=24, minutes=1))
    assert_error(user_client.get(f"{PROPOSALS}/{proposal_id}"), 404, "AI_PROPOSAL_NOT_FOUND")


def test_completed_proposals_are_kept(user_client: TestClient, ai: FakeAi, db: Session) -> None:
    insight_id = new_insight(user_client)
    proposal_id = add_proposal(db, insight_id, owner(db), S.COMPLETED, question="質問", answer="回答")
    make_old(db, proposal_id, timedelta(days=30))

    assert get(user_client, str(proposal_id))["status"] == "completed"


def test_concurrent_cleanups_return_count_once(user_client: TestClient, ai: FakeAi, db: Session) -> None:
    insight_id = new_insight(user_client)
    me = owner(db)
    # 戻しすぎが分かるよう、0 より大きい回数から始める
    set_usage(db, me, personal=3, app_count=3)
    proposal_id = add_proposal(db, insight_id, me, S.GENERATING_QUESTION, usage_date=today())
    make_old(db, proposal_id, timedelta(minutes=3))
    now = clock.now()

    def clean(i: int) -> int:
        # 定期の片付け（絞らない）と、その場の判定（利用者で絞る）を同時に動かす
        with SessionLocal() as session:
            if i % 2:
                return ai_proposals.cleanup(session, now).question_failed
            return ai_proposals.cleanup(session, now, user_id=me).question_failed

    results = in_threads(6, clean)

    assert sum(results) == 1
    assert personal_used(db, me) == 2
    assert app_used(db) == 2


def test_returning_count_uses_the_day_it_was_used(
    user_client: TestClient, ai: FakeAi, db: Session
) -> None:
    insight_id = new_insight(user_client)
    me = owner(db)
    yesterday = today() - timedelta(days=1)
    db.add_all([AiUsage(user_id=me, usage_date=yesterday, used_count=2), AppAiUsage(usage_date=yesterday, used_count=2)])
    db.commit()
    proposal_id = add_proposal(db, insight_id, me, S.GENERATING_QUESTION, usage_date=yesterday)
    make_old(db, proposal_id, timedelta(minutes=3))

    get(user_client, str(proposal_id))

    # 日付をまたいでも、+1 した日の行を戻す
    assert personal_used(db, me, yesterday) == 1
    assert app_used(db, yesterday) == 1
    assert personal_used(db, me) == 0


def test_insight_detail_cleans_up_stuck_proposal(user_client: TestClient, ai: FakeAi, db: Session) -> None:
    insight_id = new_insight(user_client)
    me = owner(db)
    set_usage(db, me, personal=1, app_count=1)
    proposal_id = add_proposal(db, insight_id, me, S.GENERATING_QUESTION, usage_date=today())
    make_old(db, proposal_id, timedelta(minutes=3))

    response = user_client.get(f"{INSIGHTS}/{insight_id}")

    assert response.status_code == 200
    assert response.json()["pending_proposal"] is None
    assert personal_used(db, me) == 0


def test_worker_cleans_up_proposals_and_old_rate_limit_events(
    user_client: TestClient, ai: FakeAi, db: Session
) -> None:
    insight_id = new_insight(user_client)
    me = owner(db)
    set_usage(db, me, personal=1, app_count=1)
    proposal_id = add_proposal(db, insight_id, me, S.GENERATING_QUESTION, usage_date=today())
    make_old(db, proposal_id, timedelta(minutes=3))
    db.execute(update(RateLimitEvent).values(occurred_at=clock.now() - timedelta(days=1, minutes=1)))
    db.add(RateLimitEvent(kind="search", subject=str(me)))
    db.commit()

    run_cleanup()

    assert proposal_row(db, proposal_id).status == S.QUESTION_FAILED
    assert personal_used(db, me) == 0
    # 1日を過ぎた回数制限の記録（接続元の IP を含む）は消え、新しいものは残る
    assert db.scalars(select(RateLimitEvent.kind)).all() == ["search"]


# ---- 本日の残り回数 GET /me/ai-usage ----


def test_usage_shows_remaining_today(user_client: TestClient, ai: FakeAi, db: Session) -> None:
    assert user_client.get(USAGE).json() == {"remaining_today": 5, "daily_limit": 5, "app_limit_reached": False}

    started(user_client, new_insight(user_client))

    assert user_client.get(USAGE).json() == {"remaining_today": 4, "daily_limit": 5, "app_limit_reached": False}


def test_usage_shows_app_limit_reached(user_client: TestClient, ai: FakeAi, db: Session) -> None:
    set_usage(db, owner(db), personal=5, app_count=100)

    assert user_client.get(USAGE).json() == {"remaining_today": 0, "daily_limit": 5, "app_limit_reached": True}


def test_usage_counts_only_own_usage(
    user_client: TestClient, other_client: TestClient, ai: FakeAi, db: Session
) -> None:
    started(other_client, new_insight(other_client))

    assert user_client.get(USAGE).json()["remaining_today"] == 5


def test_usage_cleans_up_stuck_proposals_first(user_client: TestClient, ai: FakeAi, db: Session) -> None:
    insight_id = new_insight(user_client)
    me = owner(db)
    set_usage(db, me, personal=1, app_count=1)
    proposal_id = add_proposal(db, insight_id, me, S.GENERATING_QUESTION, usage_date=today())
    make_old(db, proposal_id, timedelta(minutes=3))

    assert user_client.get(USAGE).json()["remaining_today"] == 5


def test_usage_requires_login(client: TestClient) -> None:
    assert_error(client.get(USAGE), 401, "UNAUTHENTICATED")


def test_deleting_insight_removes_its_proposals(user_client: TestClient, ai: FakeAi, db: Session) -> None:
    insight_id = new_insight(user_client)
    proposal_id = started(user_client, insight_id)

    assert user_client.delete(f"{INSIGHTS}/{insight_id}").status_code == 204

    assert_error(user_client.get(f"{PROPOSALS}/{proposal_id}"), 404, "AI_PROPOSAL_NOT_FOUND")
    assert db.scalar(select(func.count()).select_from(Insight)) == 0
