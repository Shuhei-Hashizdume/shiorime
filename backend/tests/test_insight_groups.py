"""気づき一覧・本ごとの気づき一覧（api.md 7-4）。"""

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core import clock
from app.models import Book, Insight, ProposalStatus
from tests.test_insights import add_book, add_proposal, owner, write

GROUPS = "/api/v1/insight-groups"


def set_time(db: Session, model, row_id: str, minutes: int) -> None:
    db.execute(update(model).where(model.id == uuid.UUID(row_id)).values(created_at=clock.now() + timedelta(minutes=minutes)))
    db.commit()


def titles(client: TestClient, sort: str) -> list[str]:
    return [g["title"] for g in client.get(GROUPS, params={"sort": sort}).json()["items"]]


def test_groups_include_books_without_insights_and_deleted_books(user_client: TestClient) -> None:
    empty = add_book(user_client, "気づきなし")
    gone = add_book(user_client, "削除した本")
    write(user_client, gone)
    user_client.delete(f"/api/v1/books/{gone}")

    items = {g["title"]: g for g in user_client.get(GROUPS).json()["items"]}

    assert items["気づきなし"] == {
        "id": empty,
        "title": "気づきなし",
        "cover_url": None,
        "insight_count": 0,
        "last_written_at": None,
        "deleted": False,
    }
    assert items["削除した本"]["id"] == gone
    assert items["削除した本"]["insight_count"] == 1
    assert items["削除した本"]["deleted"] is True


def test_groups_only_mine(user_client: TestClient, other_client: TestClient) -> None:
    write(other_client, add_book(other_client, "他人の本"))

    assert user_client.get(GROUPS).json() == {"items": [], "next_cursor": None}


def test_sort_orders(user_client: TestClient, db: Session) -> None:
    # A：気づき2件（古い）／B：気づき1件（新しい）／C：0件（本棚に新しく登録）／D：0件（本棚に古く登録）
    a = add_book(user_client, "A")
    b = add_book(user_client, "B")
    c = add_book(user_client, "C")
    d = add_book(user_client, "D")
    set_time(db, Book, a, -40)
    set_time(db, Book, b, -30)
    set_time(db, Book, c, -10)
    set_time(db, Book, d, -50)
    set_time(db, Insight, write(user_client, a), -20)
    set_time(db, Insight, write(user_client, a), -19)
    set_time(db, Insight, write(user_client, b), -5)

    # 最近書いた順：最後に書いた日時 → 0件の本は後ろで、登録が新しい順
    assert titles(user_client, "recent") == ["B", "A", "C", "D"]
    # 多い順：件数 → 最後に書いた日時
    assert titles(user_client, "many") == ["A", "B", "C", "D"]
    # 少ない順：件数 → 登録が新しい順
    assert titles(user_client, "few") == ["C", "D", "B", "A"]


def test_deleted_books_come_after_shelf_books_with_same_values(user_client: TestClient, db: Session) -> None:
    shelf = add_book(user_client, "本棚")
    gone = add_book(user_client, "削除")
    i1 = write(user_client, shelf)
    i2 = write(user_client, gone)
    same = clock.now()
    db.execute(update(Insight).where(Insight.id.in_([uuid.UUID(i1), uuid.UUID(i2)])).values(created_at=same))
    db.commit()
    user_client.delete(f"/api/v1/books/{gone}")

    assert titles(user_client, "recent") == ["本棚", "削除"]
    assert titles(user_client, "few") == ["本棚", "削除"]


def test_groups_cursor_pages_without_duplicates(user_client: TestClient, db: Session) -> None:
    for i in range(35):
        book_id = add_book(user_client, f"本{i:02d}")
        if i % 3 == 0:
            write(user_client, book_id)

    for sort in ("recent", "many", "few"):
        first = user_client.get(GROUPS, params={"sort": sort}).json()
        assert len(first["items"]) == 30
        second = user_client.get(GROUPS, params={"sort": sort, "cursor": first["next_cursor"]}).json()
        assert len(second["items"]) == 5
        assert second["next_cursor"] is None
        ids = [g["id"] for g in first["items"] + second["items"]]
        assert len(set(ids)) == 35


def test_groups_validation(user_client: TestClient) -> None:
    for i in range(31):
        add_book(user_client, f"本{i}")
    cursor = user_client.get(GROUPS, params={"sort": "few"}).json()["next_cursor"]

    bad_sort = user_client.get(GROUPS, params={"sort": "old"})
    assert bad_sort.json()["error"]["fields"] == [{"field": "sort", "reason": "invalid_value"}]
    # カーソルの並び順と sort が違う
    mismatch = user_client.get(GROUPS, params={"sort": "recent", "cursor": cursor})
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["fields"] == [{"field": "cursor", "reason": "invalid_format"}]
    assert user_client.get(GROUPS, params={"cursor": "broken!"}).status_code == 422


# ---- まとまり1件 ----


def test_group_detail(user_client: TestClient) -> None:
    book_id = add_book(user_client, "嫌われる勇気", "岸見一郎")
    write(user_client, book_id)

    group = user_client.get(f"{GROUPS}/{book_id}").json()

    assert group["author"] == "岸見一郎"
    assert group["insight_count"] == 1
    assert group["deleted"] is False


def test_group_not_found_cases(user_client: TestClient, other_client: TestClient) -> None:
    others = add_book(other_client)
    gone = add_book(user_client)
    insight_id = write(user_client, gone)
    user_client.delete(f"/api/v1/books/{gone}")
    # 削除済みの本で、最後の気づきも消した
    user_client.delete(f"/api/v1/insights/{insight_id}")

    for group_id in (others, gone, str(uuid.uuid4())):
        for url in (f"{GROUPS}/{group_id}", f"{GROUPS}/{group_id}/insights"):
            response = user_client.get(url)
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "INSIGHT_GROUP_NOT_FOUND"


# ---- 本ごとの気づき一覧（カード） ----


def test_cards_newest_first_with_next_step_count(user_client: TestClient, db: Session) -> None:
    book_id = add_book(user_client)
    old = write(user_client, book_id, "古い", page=10, quote="引用")
    new = write(user_client, book_id, "新しい")
    set_time(db, Insight, old, -10)
    uid = owner(db)
    add_proposal(db, old, uid, ProposalStatus.COMPLETED)
    # 完了していないAI提案は数えない
    add_proposal(db, new, uid, ProposalStatus.GENERATING_PLANS, answer="回答")

    body = user_client.get(f"{GROUPS}/{book_id}/insights").json()

    assert [(c["body"], c["next_step_count"]) for c in body["items"]] == [("新しい", 0), ("古い", 2)]
    assert body["items"][1]["page"] == 10
    assert body["items"][1]["quote"] == "引用"
    assert body["next_cursor"] is None


def test_cards_empty_group_and_paging(user_client: TestClient) -> None:
    book_id = add_book(user_client)
    assert user_client.get(f"{GROUPS}/{book_id}/insights").json() == {"items": [], "next_cursor": None}

    for i in range(21):
        write(user_client, book_id, f"気づき{i}")
    first = user_client.get(f"{GROUPS}/{book_id}/insights").json()
    second = user_client.get(f"{GROUPS}/{book_id}/insights", params={"cursor": first["next_cursor"]}).json()
    assert len(first["items"]) == 20
    assert len(second["items"]) == 1
    assert len({c["id"] for c in first["items"] + second["items"]}) == 21


def test_cards_of_deleted_book_are_still_visible(user_client: TestClient) -> None:
    book_id = add_book(user_client)
    write(user_client, book_id)
    user_client.delete(f"/api/v1/books/{book_id}")

    assert len(user_client.get(f"{GROUPS}/{book_id}/insights").json()["items"]) == 1
    assert user_client.get(f"{GROUPS}/{book_id}").json()["deleted"] is True
