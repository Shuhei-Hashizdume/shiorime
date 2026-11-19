"""本棚（api.md 7-3）。どの処理も、まず「自分の本か」で絞る（他人の本は 404）。"""

import base64
import binascii
import json
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, delete, func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Book, Insight, ReadingStatus
from app.schemas.book import BookDetail, CatalogItem
from app.services import rate_limit
from app.services.google_books import GoogleBooksClient

PAGE_SIZE = 30
SEARCH_PAGE_SIZE = 20


def book_not_found() -> AppError:
    return AppError(404, "BOOK_NOT_FOUND", "本が見つかりません")


# ---- 一覧（カーソルで続きを読む。api.md 1-5） ----


def encode_cursor(created_at: datetime, book_id: uuid.UUID) -> str:
    raw = json.dumps({"c": created_at.isoformat(), "i": str(book_id)}).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        data = json.loads(raw)
        return datetime.fromisoformat(data["c"]), uuid.UUID(data["i"])
    except (binascii.Error, ValueError, KeyError, TypeError):
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "cursor が正しくありません",
            fields=[{"field": "cursor", "reason": "invalid_format"}],
        ) from None


@dataclass
class BookPage:
    items: list[Book]
    total: int
    next_cursor: str | None


def list_books(
    db: Session, user_id: uuid.UUID, status: ReadingStatus | None, cursor: str | None
) -> BookPage:
    conditions = [Book.user_id == user_id]
    if status is not None:
        conditions.append(Book.status == status)

    # 冊数も件数の絞り込みもデータベースで行う（全部取ってきて Python で数えない）
    total = db.scalar(select(func.count()).select_from(Book).where(*conditions)) or 0

    query: Select[tuple[Book]] = select(Book).where(*conditions)
    if cursor is not None:
        created_at, book_id = decode_cursor(cursor)
        query = query.where(tuple_(Book.created_at, Book.id) < tuple_(created_at, book_id))
    # 続きがあるかを知るために1冊多く取る
    rows = list(db.scalars(query.order_by(Book.created_at.desc(), Book.id.desc()).limit(PAGE_SIZE + 1)))

    next_cursor = None
    if len(rows) > PAGE_SIZE:
        rows = rows[:PAGE_SIZE]
        next_cursor = encode_cursor(rows[-1].created_at, rows[-1].id)
    return BookPage(items=rows, total=total, next_cursor=next_cursor)


# ---- 詳細 ----


def _detail(db: Session, book: Book) -> BookDetail:
    insight_count = db.scalar(
        select(func.count()).select_from(Insight).where(Insight.book_id == book.id, Insight.user_id == book.user_id)
    )
    return BookDetail(
        id=book.id,
        title=book.title,
        author=book.author,
        cover_url=book.cover_url,
        status=ReadingStatus(book.status),
        google_volume_id=book.google_volume_id,
        insight_count=insight_count or 0,
    )


def get_book(db: Session, user_id: uuid.UUID, book_id: uuid.UUID) -> BookDetail:
    book = db.scalars(select(Book).where(Book.id == book_id, Book.user_id == user_id)).one_or_none()
    if book is None:
        raise book_not_found()
    return _detail(db, book)


# ---- 追加 ----


def create_manual_book(
    db: Session, user_id: uuid.UUID, *, title: str, author: str | None, status: ReadingStatus
) -> uuid.UUID:
    # 手入力の本は重複を判定しない（要件定義書 5.2）
    book_id = db.scalar(
        insert(Book)
        .values(user_id=user_id, title=title, author=author, status=status.value)
        .returning(Book.id)
    )
    db.commit()
    assert book_id is not None
    return book_id


def _shelf_book_id(db: Session, user_id: uuid.UUID, google_volume_id: str) -> uuid.UUID | None:
    return db.scalar(
        select(Book.id).where(Book.user_id == user_id, Book.google_volume_id == google_volume_id)
    )


def _already_on_shelf(book_id: uuid.UUID) -> AppError:
    return AppError(
        409,
        "BOOK_ALREADY_ON_SHELF",
        "この本は既に本棚にあります",
        details={"book_id": str(book_id)},
    )


def create_catalog_book(
    db: Session,
    user_id: uuid.UUID,
    google_books: GoogleBooksClient,
    *,
    google_volume_id: str,
    status: ReadingStatus,
) -> uuid.UUID:
    # 本棚にすでにあれば、Google Books に聞かずにすぐ断る（早期リターン）
    existing = _shelf_book_id(db, user_id, google_volume_id)
    if existing is not None:
        raise _already_on_shelf(existing)

    # 改ざんを防ぐため、タイトルなどは画面から受け取らず Google Books から取り直す
    catalog_book = google_books.get_volume(google_volume_id)
    if catalog_book is None:
        raise AppError(404, "CATALOG_BOOK_NOT_FOUND", "Google Books にその本がありません")

    # Google Books に聞いている間に別の端末で同じ本が入った場合も、一意制約で1冊だけにする
    book_id = db.scalar(
        insert(Book)
        .values(
            user_id=user_id,
            title=catalog_book.title,
            author=catalog_book.authors,
            cover_url=catalog_book.cover_url,
            google_volume_id=google_volume_id,
            isbn=catalog_book.isbn,
            status=status.value,
        )
        .on_conflict_do_nothing(index_elements=[Book.user_id, Book.google_volume_id])
        .returning(Book.id)
    )
    if book_id is None:
        db.rollback()
        existing = _shelf_book_id(db, user_id, google_volume_id)
        assert existing is not None
        raise _already_on_shelf(existing)
    db.commit()
    return book_id


# ---- 変更 ----


def update_book(
    db: Session, user_id: uuid.UUID, book_id: uuid.UUID, changes: dict[str, str | None]
) -> BookDetail:
    """手入力の本のタイトル・著者を変え、その本の気づきの写しも同じトランザクションで書き換える。"""
    # 「自分の・手入力の本なら書き換える」を1回の命令で行う
    book = db.scalars(
        update(Book)
        .where(Book.id == book_id, Book.user_id == user_id, Book.google_volume_id.is_(None))
        .values(**changes)
        .returning(Book)
    ).one_or_none()

    if book is None:
        db.rollback()
        exists = db.scalar(select(Book.id).where(Book.id == book_id, Book.user_id == user_id))
        if exists is None:
            raise book_not_found()
        raise AppError(409, "BOOK_NOT_EDITABLE", "Google Books から追加した本は編集できません")

    copies = {f"book_{key}": value for key, value in changes.items()}
    db.execute(update(Insight).where(Insight.book_id == book_id, Insight.user_id == user_id).values(**copies))
    db.commit()
    return _detail(db, book)


def update_status(db: Session, user_id: uuid.UUID, book_id: uuid.UUID, status: ReadingStatus) -> BookDetail:
    book = db.scalars(
        update(Book)
        .where(Book.id == book_id, Book.user_id == user_id)
        .values(status=status.value)
        .returning(Book)
    ).one_or_none()
    if book is None:
        db.rollback()
        raise book_not_found()
    db.commit()
    return _detail(db, book)


# ---- 削除 ----


def delete_book(db: Session, user_id: uuid.UUID, book_id: uuid.UUID) -> None:
    # 気づきは残り、book_id は NULL になる（ON DELETE SET NULL）
    deleted = db.scalar(delete(Book).where(Book.id == book_id, Book.user_id == user_id).returning(Book.id))
    if deleted is None:
        db.rollback()
        raise book_not_found()
    db.commit()


# ---- 検索（Google Books） ----


def search_catalog(
    db: Session, user_id: uuid.UUID, google_books: GoogleBooksClient, *, q: str, offset: int
) -> tuple[list[CatalogItem], int | None]:
    rate_limit.reserve(db, rate_limit.SEARCH, str(user_id))

    # Google Books は1回に20件までしか返さないので、20件ちょうど返ってきたら続きがあるとみなす。
    # 結果が20の倍数で終わるときだけ、続きを頼むと0件になる（そのときは next_offset が null になる）
    found = google_books.search(q, offset, SEARCH_PAGE_SIZE)[:SEARCH_PAGE_SIZE]
    has_more = len(found) == SEARCH_PAGE_SIZE

    # 20冊分を1回でまとめて聞く（1冊ずつ聞くと N＋1 になる）
    volume_ids = [b.google_volume_id for b in found]
    on_shelf: dict[str, uuid.UUID] = {}
    if volume_ids:
        rows = db.execute(
            select(Book.google_volume_id, Book.id).where(
                Book.user_id == user_id, Book.google_volume_id.in_(volume_ids)
            )
        )
        on_shelf = {volume_id: book_id for volume_id, book_id in rows if volume_id is not None}

    items = [
        CatalogItem(
            google_volume_id=b.google_volume_id,
            title=b.title,
            authors=b.authors,
            published_year=b.published_year,
            cover_url=b.cover_url,
            info_link=b.info_link,
            shelf_book_id=on_shelf.get(b.google_volume_id),
        )
        for b in found
    ]
    return items, (offset + SEARCH_PAGE_SIZE if has_more else None)
