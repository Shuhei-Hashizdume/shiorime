import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.book import BOOK_AUTHOR_MAX_CHARS, BOOK_TITLE_MAX_CHARS

INSIGHT_BODY_MAX_CHARS = 1000
INSIGHT_QUOTE_MAX_CHARS = 300
INSIGHT_PAGE_MIN = 1
INSIGHT_PAGE_MAX = 9999


class Insight(Base):
    """気づき（database.md 3-3）。

    テーブルは機能2で作る（本の詳細の件数・本の編集での写しの書き換えに使うため）。API は機能3で作る。
    """

    __tablename__ = "insights"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # 本を削除すると NULL になる（本棚から削除済みの目印）
    book_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("books.id", ondelete="SET NULL"))
    # 本を削除しても残す元の本の ID（外部キーにしない）
    original_book_id: Mapped[uuid.UUID]
    book_title: Mapped[str]
    book_author: Mapped[str | None]
    book_cover_url: Mapped[str | None]
    quote: Mapped[str | None]
    page: Mapped[int | None]
    body: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        CheckConstraint(f"char_length(book_title) <= {BOOK_TITLE_MAX_CHARS * 4}", name="book_title_max_length"),
        CheckConstraint(
            f"char_length(book_author) <= {BOOK_AUTHOR_MAX_CHARS * 4}", name="book_author_max_length"
        ),
        CheckConstraint("quote <> ''", name="quote_not_empty"),
        CheckConstraint(f"char_length(quote) <= {INSIGHT_QUOTE_MAX_CHARS * 4}", name="quote_max_length"),
        CheckConstraint(f"page BETWEEN {INSIGHT_PAGE_MIN} AND {INSIGHT_PAGE_MAX}", name="page_range"),
        CheckConstraint("body <> ''", name="body_not_empty"),
        CheckConstraint(f"char_length(body) <= {INSIGHT_BODY_MAX_CHARS * 4}", name="body_max_length"),
        # 本ごとの気づき一覧（database.md 4-2 の 2）
        Index("ix_insights_user_id_original_book_id_created_at_id", "user_id", "original_book_id", "created_at", "id"),
        # 本の削除（ON DELETE SET NULL）で、その本の気づきを探す（database.md 4-2 の 3）
        Index("ix_insights_book_id", "book_id"),
    )
