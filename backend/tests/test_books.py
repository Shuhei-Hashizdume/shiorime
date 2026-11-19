"""本棚（api.md 7-3）。"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.core import clock
from app.main import app
from app.models import Book, Insight, User
from app.services.google_books import failed_error, limit_error
from tests.fakes import FakeGoogleBooks, catalog_book

BOOKS = "/api/v1/books"


def add_manual(client: TestClient, title: str = "手入力の本", **overrides) -> str:
    body = {"title": title, "status": "reading", **overrides}
    response = client.post(BOOKS, json=body)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def add_catalog(client: TestClient, volume_id: str, status: str = "reading"):
    return client.post(f"{BOOKS}/from-catalog", json={"google_volume_id": volume_id, "status": status})


def user_id(db: Session, email: str = "reader@example.com") -> uuid.UUID:
    return db.scalar(select(User.id).where(User.email == email))


def add_insight(db: Session, book_id: str, owner: uuid.UUID, title: str = "手入力の本") -> uuid.UUID:
    insight_id = db.scalar(
        insert(Insight)
        .values(
            user_id=owner,
            book_id=uuid.UUID(book_id),
            original_book_id=uuid.UUID(book_id),
            book_title=title,
            body="気づき",
        )
        .returning(Insight.id)
    )
    db.commit()
    return insight_id


# ---- 手入力で追加 ----


def test_create_manual_book(user_client: TestClient) -> None:
    response = user_client.post(BOOKS, json={"title": "  がくもん  ", "author": " ", "status": "finished"})

    assert response.status_code == 201
    book_id = response.json()["id"]
    assert response.headers["location"] == f"/api/v1/books/{book_id}"

    detail = user_client.get(f"{BOOKS}/{book_id}").json()
    assert detail == {
        "id": book_id,
        "title": "がくもん",  # 前後の空白を除き、NFC にそろえる
        "author": None,  # 空白だけの著者は NULL
        "cover_url": None,
        "status": "finished",
        "google_volume_id": None,
        "insight_count": 0,
    }


def test_manual_book_validation(user_client: TestClient) -> None:
    response = user_client.post(BOOKS, json={"title": "あ" * 201, "author": "い" * 101, "status": "unread", "x": 1})

    assert response.status_code == 422
    assert sorted(response.json()["error"]["fields"], key=lambda f: f["field"]) == [
        {"field": "author", "reason": "too_long", "limit": 100},
        {"field": "status", "reason": "invalid_value"},
        {"field": "title", "reason": "too_long", "limit": 200},
        {"field": "x", "reason": "not_allowed"},
    ]


def test_manual_book_title_boundaries(user_client: TestClient) -> None:
    assert user_client.post(BOOKS, json={"title": "あ" * 200, "status": "reading"}).status_code == 201
    response = user_client.post(BOOKS, json={"title": "   ", "status": "reading"})
    assert response.status_code == 422
    assert response.json()["error"]["fields"] == [{"field": "title", "reason": "required"}]


def test_manual_books_can_be_duplicated(user_client: TestClient) -> None:
    add_manual(user_client, "同じ本")
    add_manual(user_client, "同じ本")

    assert user_client.get(BOOKS).json()["total"] == 2


def test_books_require_login(client: TestClient) -> None:
    assert client.get(BOOKS).status_code == 401
    assert client.post(BOOKS, json={"title": "本", "status": "reading"}).status_code == 401


# ---- 検索結果から追加 ----


def test_create_catalog_book_fetches_from_google(user_client: TestClient, google_books: FakeGoogleBooks) -> None:
    google_books.add(catalog_book("vol1"))

    response = add_catalog(user_client, "vol1")

    assert response.status_code == 201
    detail = user_client.get(f"{BOOKS}/{response.json()['id']}").json()
    assert detail["title"] == "嫌われる勇気"
    assert detail["author"] == "岸見一郎、古賀史健"
    assert detail["google_volume_id"] == "vol1"
    assert google_books.get_calls == ["vol1"]


def test_catalog_book_rejects_extra_fields(user_client: TestClient, google_books: FakeGoogleBooks) -> None:
    response = user_client.post(
        f"{BOOKS}/from-catalog", json={"google_volume_id": "vol1", "status": "reading", "title": "改ざん"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == [{"field": "title", "reason": "not_allowed"}]


def test_catalog_book_rejects_strange_volume_id(user_client: TestClient, google_books: FakeGoogleBooks) -> None:
    response = add_catalog(user_client, "../../etc")

    assert response.status_code == 422
    assert response.json()["error"]["fields"][0]["reason"] == "invalid_format"


def test_duplicate_catalog_book_returns_409_without_calling_google(
    user_client: TestClient, google_books: FakeGoogleBooks
) -> None:
    google_books.add(catalog_book("vol1"))
    first = add_catalog(user_client, "vol1").json()["id"]
    google_books.get_calls.clear()

    response = add_catalog(user_client, "vol1")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "BOOK_ALREADY_ON_SHELF"
    assert response.json()["error"]["details"] == {"book_id": first}
    assert google_books.get_calls == []


def test_other_user_can_add_same_catalog_book(
    user_client: TestClient, other_client: TestClient, google_books: FakeGoogleBooks
) -> None:
    google_books.add(catalog_book("vol1"))

    assert add_catalog(user_client, "vol1").status_code == 201
    assert add_catalog(other_client, "vol1").status_code == 201


def test_unknown_catalog_book(user_client: TestClient, google_books: FakeGoogleBooks) -> None:
    response = add_catalog(user_client, "nothing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CATALOG_BOOK_NOT_FOUND"


def test_google_books_errors_when_adding(user_client: TestClient, google_books: FakeGoogleBooks) -> None:
    google_books.error = limit_error()
    assert add_catalog(user_client, "vol1").json()["error"]["code"] == "BOOK_SEARCH_LIMIT"

    google_books.error = failed_error()
    response = add_catalog(user_client, "vol1")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "BOOK_SEARCH_FAILED"


def test_concurrent_catalog_adds_create_one_book(
    user_client: TestClient, google_books: FakeGoogleBooks, db: Session
) -> None:
    google_books.add(catalog_book("vol1"))
    cookies = dict(user_client.cookies)

    def send(_: int) -> int:
        with TestClient(app, base_url="https://testserver", cookies=cookies) as c:
            return add_catalog(c, "vol1").status_code

    with ThreadPoolExecutor(max_workers=5) as pool:
        statuses = list(pool.map(send, range(5)))

    assert statuses.count(201) == 1
    assert statuses.count(409) == 4
    assert db.scalar(select(func.count()).select_from(Book)) == 1


# ---- 一覧 ----


def test_list_books_newest_first_with_cursor(user_client: TestClient, db: Session) -> None:
    owner = user_id(db)
    base = clock.now()
    # 31冊（同じ日時の本も混ぜて、ID で順番が決まることも確かめる）
    for i in range(31):
        db.execute(
            insert(Book).values(
                user_id=owner,
                title=f"本{i:02d}",
                status="reading" if i % 2 else "finished",
                created_at=base + timedelta(seconds=i // 2),
            )
        )
    db.commit()

    first = user_client.get(BOOKS).json()
    assert first["total"] == 31
    assert len(first["items"]) == 30
    assert first["next_cursor"] is not None
    assert set(first["items"][0]) == {"id", "title", "cover_url", "status"}

    second = user_client.get(BOOKS, params={"cursor": first["next_cursor"]}).json()
    assert second["total"] == 31
    assert len(second["items"]) == 1
    assert second["next_cursor"] is None

    ids = [b["id"] for b in first["items"] + second["items"]]
    assert len(set(ids)) == 31  # 2回出たり飛ばされたりしない
    titles = [b["title"] for b in first["items"] + second["items"]]
    assert titles[0] in ("本30",)
    assert titles[-1] in ("本00", "本01")


def test_list_books_filter_by_status(user_client: TestClient) -> None:
    add_manual(user_client, "読書中", status="reading")
    add_manual(user_client, "読了", status="finished")

    reading = user_client.get(BOOKS, params={"status": "reading"}).json()
    assert reading["total"] == 1
    assert [b["title"] for b in reading["items"]] == ["読書中"]
    assert user_client.get(BOOKS).json()["total"] == 2


def test_list_books_validation(user_client: TestClient) -> None:
    bad_status = user_client.get(BOOKS, params={"status": "unread"})
    assert bad_status.status_code == 422
    assert bad_status.json()["error"]["fields"] == [{"field": "status", "reason": "invalid_value"}]

    bad_cursor = user_client.get(BOOKS, params={"cursor": "broken!!"})
    assert bad_cursor.status_code == 422
    assert bad_cursor.json()["error"]["fields"] == [{"field": "cursor", "reason": "invalid_format"}]


def test_list_shows_only_my_books(user_client: TestClient, other_client: TestClient) -> None:
    add_manual(other_client, "他人の本")

    assert user_client.get(BOOKS).json() == {"items": [], "total": 0, "next_cursor": None}


# ---- 詳細・他人の本 ----


def test_detail_counts_insights(user_client: TestClient, db: Session) -> None:
    book_id = add_manual(user_client)
    owner = user_id(db)
    add_insight(db, book_id, owner)
    add_insight(db, book_id, owner)

    assert user_client.get(f"{BOOKS}/{book_id}").json()["insight_count"] == 2


def test_other_users_book_is_404_everywhere(user_client: TestClient, other_client: TestClient) -> None:
    book_id = add_manual(other_client)
    url = f"{BOOKS}/{book_id}"

    responses = [
        user_client.get(url),
        user_client.patch(url, json={"title": "乗っ取り"}),
        user_client.put(f"{url}/status", json={"status": "finished"}),
        user_client.delete(url),
    ]

    for response in responses:
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "BOOK_NOT_FOUND"
    assert other_client.get(url).json()["title"] == "手入力の本"


def test_book_id_must_be_uuid(user_client: TestClient) -> None:
    response = user_client.get(f"{BOOKS}/not-a-uuid")

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == [{"field": "book_id", "reason": "invalid_format"}]


# ---- 変更 ----


def test_update_manual_book_also_updates_insight_copies(user_client: TestClient, db: Session) -> None:
    book_id = add_manual(user_client, "古いタイトル", author="古い著者")
    insight_id = add_insight(db, book_id, user_id(db), title="古いタイトル")

    response = user_client.patch(f"{BOOKS}/{book_id}", json={"title": " 新しいタイトル ", "author": ""})

    assert response.status_code == 200
    assert response.json()["title"] == "新しいタイトル"
    assert response.json()["author"] is None
    db.expire_all()
    insight = db.get(Insight, insight_id)
    assert insight.book_title == "新しいタイトル"
    assert insight.book_author is None


def test_update_only_author_keeps_title(user_client: TestClient) -> None:
    book_id = add_manual(user_client, "そのまま")

    response = user_client.patch(f"{BOOKS}/{book_id}", json={"author": "新しい著者"})

    assert response.json()["title"] == "そのまま"
    assert response.json()["author"] == "新しい著者"


def test_update_validation(user_client: TestClient) -> None:
    book_id = add_manual(user_client)

    assert user_client.patch(f"{BOOKS}/{book_id}", json={}).status_code == 422
    assert user_client.patch(f"{BOOKS}/{book_id}", json={"title": None}).status_code == 422
    assert user_client.patch(f"{BOOKS}/{book_id}", json={"title": " "}).status_code == 422
    assert user_client.patch(f"{BOOKS}/{book_id}", json={"status": "finished"}).status_code == 422


def test_catalog_book_is_not_editable(user_client: TestClient, google_books: FakeGoogleBooks) -> None:
    google_books.add(catalog_book("vol1"))
    book_id = add_catalog(user_client, "vol1").json()["id"]

    response = user_client.patch(f"{BOOKS}/{book_id}", json={"title": "書き換え"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "BOOK_NOT_EDITABLE"
    assert user_client.get(f"{BOOKS}/{book_id}").json()["title"] == "嫌われる勇気"


def test_update_status(user_client: TestClient) -> None:
    book_id = add_manual(user_client)

    response = user_client.put(f"{BOOKS}/{book_id}/status", json={"status": "finished"})

    assert response.status_code == 200
    assert response.json()["status"] == "finished"
    # 何度送っても同じ結果（冪等）
    assert user_client.put(f"{BOOKS}/{book_id}/status", json={"status": "finished"}).json()["status"] == "finished"


# ---- 削除 ----


def test_delete_keeps_insights(user_client: TestClient, db: Session) -> None:
    book_id = add_manual(user_client)
    insight_id = add_insight(db, book_id, user_id(db))

    assert user_client.delete(f"{BOOKS}/{book_id}").status_code == 204
    assert user_client.get(f"{BOOKS}/{book_id}").status_code == 404
    # 2回目は 404（本がない状態は変わらない）
    assert user_client.delete(f"{BOOKS}/{book_id}").status_code == 404

    db.expire_all()
    insight = db.get(Insight, insight_id)
    assert insight is not None
    assert insight.book_id is None
    assert insight.original_book_id == uuid.UUID(book_id)


def test_withdrawn_user_books_are_deleted(user_client: TestClient, db: Session) -> None:
    add_manual(user_client)
    db.execute(delete(User))
    db.commit()

    assert db.scalar(select(func.count()).select_from(Book)) == 0
