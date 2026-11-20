"""気づき（api.md 7-5）。"""

import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.core import clock
from app.models import AiProposal, Insight, ProposalStatus, User

BOOKS = "/api/v1/books"
INSIGHTS = "/api/v1/insights"


def add_book(client: TestClient, title: str = "嫌われる勇気", author: str | None = "岸見一郎") -> str:
    response = client.post(BOOKS, json={"title": title, "author": author, "status": "reading"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def write(client: TestClient, book_id: str, body: str = "気づきの本文", **extra) -> str:
    response = client.post(INSIGHTS, json={"book_id": book_id, "body": body, **extra})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def owner(db: Session, email: str = "reader@example.com") -> uuid.UUID:
    return db.scalar(select(User.id).where(User.email == email))


def add_proposal(db: Session, insight_id: str, user_id: uuid.UUID, status: ProposalStatus, **values) -> uuid.UUID:
    row = {
        "user_id": user_id,
        "insight_id": uuid.UUID(insight_id),
        "status": status.value,
        "insight_body": "気づきの本文",
        "idempotency_key": uuid.uuid4(),
        "usage_date": date.today(),
        **values,
    }
    if status is ProposalStatus.COMPLETED:
        row.setdefault("plans", [{"text": "次の会議で発言する"}, {"text": "気持ちをメモする"}])
        row.setdefault("completed_at", clock.now())
    proposal_id = db.scalar(insert(AiProposal).values(**row).returning(AiProposal.id))
    db.commit()
    return proposal_id


# ---- 書く ----


def test_create_insight_copies_book(user_client: TestClient, db: Session) -> None:
    book_id = add_book(user_client)

    response = user_client.post(
        INSIGHTS,
        json={"book_id": book_id, "page": 142, "quote": " 他者の課題には踏み込まない ", "body": " 本文 "},
    )

    assert response.status_code == 201
    insight_id = response.json()["id"]
    assert response.headers["location"] == f"/api/v1/insights/{insight_id}"
    insight = db.get(Insight, uuid.UUID(insight_id))
    assert insight.book_id == insight.original_book_id == uuid.UUID(book_id)
    assert (insight.book_title, insight.book_author) == ("嫌われる勇気", "岸見一郎")
    assert (insight.quote, insight.body, insight.page) == ("他者の課題には踏み込まない", "本文", 142)


def test_create_insight_optional_fields(user_client: TestClient) -> None:
    book_id = add_book(user_client)
    insight_id = write(user_client, book_id, quote="   ")

    detail = user_client.get(f"{INSIGHTS}/{insight_id}").json()
    assert detail["quote"] is None
    assert detail["page"] is None


def test_create_insight_validation(user_client: TestClient) -> None:
    book_id = add_book(user_client)

    response = user_client.post(
        INSIGHTS,
        json={"book_id": book_id, "page": 10000, "quote": "あ" * 301, "body": "い" * 1001, "book_title": "x"},
    )

    assert response.status_code == 422
    assert sorted(response.json()["error"]["fields"], key=lambda f: f["field"]) == [
        {"field": "body", "reason": "too_long", "limit": 1000},
        {"field": "book_title", "reason": "not_allowed"},
        {"field": "page", "reason": "out_of_range", "min": 1, "max": 9999},
        {"field": "quote", "reason": "too_long", "limit": 300},
    ]


def test_body_and_page_boundaries(user_client: TestClient) -> None:
    book_id = add_book(user_client)
    assert user_client.post(INSIGHTS, json={"book_id": book_id, "body": "あ" * 1000}).status_code == 201
    assert user_client.post(INSIGHTS, json={"book_id": book_id, "body": "あ", "page": 1}).status_code == 201
    assert user_client.post(INSIGHTS, json={"book_id": book_id, "body": "あ", "page": 9999}).status_code == 201
    assert user_client.post(INSIGHTS, json={"book_id": book_id, "body": "あ", "page": 0}).status_code == 422
    blank = user_client.post(INSIGHTS, json={"book_id": book_id, "body": "  "})
    assert blank.json()["error"]["fields"] == [{"field": "body", "reason": "required"}]


def test_cannot_write_on_other_users_or_deleted_book(user_client: TestClient, other_client: TestClient) -> None:
    others_book = add_book(other_client)
    my_book = add_book(user_client)
    user_client.delete(f"{BOOKS}/{my_book}")

    for book_id in (others_book, my_book, str(uuid.uuid4())):
        response = user_client.post(INSIGHTS, json={"book_id": book_id, "body": "本文"})
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "BOOK_NOT_FOUND"


# ---- 詳細 ----


def test_insight_detail(user_client: TestClient) -> None:
    book_id = add_book(user_client)
    insight_id = write(user_client, book_id, page=3, quote="引用")

    detail = user_client.get(f"{INSIGHTS}/{insight_id}").json()

    assert detail["book"] == {"id": book_id, "title": "嫌われる勇気", "author": "岸見一郎", "cover_url": None}
    assert (detail["page"], detail["quote"], detail["body"]) == (3, "引用", "気づきの本文")
    assert detail["latest_proposal"] is None
    assert detail["pending_proposal"] is None


def test_detail_proposals(user_client: TestClient, db: Session) -> None:
    insight_id = write(user_client, add_book(user_client))
    uid = owner(db)
    completed = add_proposal(db, insight_id, uid, ProposalStatus.COMPLETED)
    processing = add_proposal(db, insight_id, uid, ProposalStatus.GENERATING_PLANS, answer="回答")

    detail = user_client.get(f"{INSIGHTS}/{insight_id}").json()

    assert detail["latest_proposal"]["id"] == str(completed)
    assert detail["latest_proposal"]["plans"] == [{"text": "次の会議で発言する"}, {"text": "気持ちをメモする"}]
    assert detail["pending_proposal"] == {"id": str(processing), "status": "processing"}


def test_detail_failed_and_awaiting(user_client: TestClient, db: Session) -> None:
    uid = owner(db)
    failed_insight = write(user_client, add_book(user_client, "本1"))
    failed = add_proposal(db, failed_insight, uid, ProposalStatus.AWAITING_ANSWER, answer="回答", question="問い")
    waiting_insight = write(user_client, add_book(user_client, "本2"))
    add_proposal(db, waiting_insight, uid, ProposalStatus.AWAITING_ANSWER, question="問い")

    # 回答が入った回答待ち＝行動プランの作成に失敗
    assert user_client.get(f"{INSIGHTS}/{failed_insight}").json()["pending_proposal"] == {
        "id": str(failed),
        "status": "failed",
    }
    # まだ回答していない回答待ちは含めない
    assert user_client.get(f"{INSIGHTS}/{waiting_insight}").json()["pending_proposal"] is None


def test_other_users_insight_is_404_everywhere(user_client: TestClient, other_client: TestClient) -> None:
    insight_id = write(other_client, add_book(other_client))
    url = f"{INSIGHTS}/{insight_id}"

    for response in (user_client.get(url), user_client.patch(url, json={"body": "乗っ取り"}), user_client.delete(url)):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "INSIGHT_NOT_FOUND"
    assert other_client.get(url).json()["body"] == "気づきの本文"


# ---- 変更 ----


def test_partial_update(user_client: TestClient) -> None:
    insight_id = write(user_client, add_book(user_client), page=5, quote="引用")
    url = f"{INSIGHTS}/{insight_id}"

    # 本文だけ送ると、引用とページは変わらない
    assert user_client.patch(url, json={"body": "新しい本文"}).status_code == 204
    detail = user_client.get(url).json()
    assert (detail["body"], detail["quote"], detail["page"]) == ("新しい本文", "引用", 5)

    # null・空文字で消す
    assert user_client.patch(url, json={"quote": "", "page": None}).status_code == 204
    detail = user_client.get(url).json()
    assert (detail["quote"], detail["page"]) == (None, None)


def test_update_validation(user_client: TestClient) -> None:
    url = f"{INSIGHTS}/{write(user_client, add_book(user_client))}"

    assert user_client.patch(url, json={"body": None}).json()["error"]["fields"][0]["reason"] == "required"
    assert user_client.patch(url, json={"body": ""}).status_code == 422
    assert user_client.patch(url, json={"page": ""}).status_code == 422
    assert user_client.patch(url, json={"book_id": str(uuid.uuid4())}).status_code == 422
    assert user_client.patch(url, json={}).status_code == 204


def test_can_edit_insight_of_deleted_book(user_client: TestClient) -> None:
    book_id = add_book(user_client)
    insight_id = write(user_client, book_id)
    user_client.delete(f"{BOOKS}/{book_id}")

    assert user_client.patch(f"{INSIGHTS}/{insight_id}", json={"body": "削除後に編集"}).status_code == 204
    detail = user_client.get(f"{INSIGHTS}/{insight_id}").json()
    assert detail["body"] == "削除後に編集"
    assert detail["book"]["title"] == "嫌われる勇気"


# ---- 削除 ----


def test_delete_insight_also_deletes_proposals(user_client: TestClient, db: Session) -> None:
    insight_id = write(user_client, add_book(user_client))
    add_proposal(db, insight_id, owner(db), ProposalStatus.GENERATING_PLANS, answer="回答")

    assert user_client.delete(f"{INSIGHTS}/{insight_id}").status_code == 204
    assert user_client.delete(f"{INSIGHTS}/{insight_id}").status_code == 404
    assert db.scalar(select(func.count()).select_from(AiProposal)) == 0


def test_completed_proposal_is_one_per_insight(user_client: TestClient, db: Session) -> None:
    insight_id = write(user_client, add_book(user_client))
    uid = owner(db)
    add_proposal(db, insight_id, uid, ProposalStatus.COMPLETED)

    import pytest
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        add_proposal(db, insight_id, uid, ProposalStatus.COMPLETED, completed_at=clock.now() + timedelta(seconds=1))
    db.rollback()
