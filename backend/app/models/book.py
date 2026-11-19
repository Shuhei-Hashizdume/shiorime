import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

BOOK_TITLE_MAX_CHARS = 200
BOOK_AUTHOR_MAX_CHARS = 100


class ReadingStatus(StrEnum):
    """読書ステータス（api.md 7-3）"""

    READING = "reading"
    FINISHED = "finished"


_status_values = ", ".join(f"'{s.value}'" for s in ReadingStatus)


class Book(Base):
    """本棚の本（database.md 3-2）。"""

    __tablename__ = "books"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str]
    author: Mapped[str | None]
    cover_url: Mapped[str | None]
    # 手入力の本は NULL。NULL かどうかで手入力の本か（編集できるか）を判断する
    google_volume_id: Mapped[str | None]
    isbn: Mapped[str | None]
    status: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        CheckConstraint("title <> ''", name="title_not_empty"),
        CheckConstraint(f"char_length(title) <= {BOOK_TITLE_MAX_CHARS * 4}", name="title_max_length"),
        CheckConstraint(f"char_length(author) <= {BOOK_AUTHOR_MAX_CHARS * 4}", name="author_max_length"),
        CheckConstraint("isbn ~ '^[0-9]{13}$'", name="isbn_13_digits"),
        CheckConstraint(f"status IN ({_status_values})", name="status_valid"),
        # 同じ人が同じ Google Books の本を2回入れられない。NULL（手入力）どうしは重複とみなされない
        UniqueConstraint("user_id", "google_volume_id", name="uq_books_user_id_google_volume_id"),
        # 本棚の一覧：自分の本で絞り、登録日時で並べる（database.md 4-2 の 1）
        Index("ix_books_user_id_created_at_id", "user_id", "created_at", "id"),
    )
