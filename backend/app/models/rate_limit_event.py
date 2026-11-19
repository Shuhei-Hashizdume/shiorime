import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RateLimitKind(StrEnum):
    LOGIN = "login"
    REGISTER = "register"
    SEARCH = "search"
    PASSWORD_CONFIRM = "password_confirm"


_kind_values = ", ".join(f"'{k.value}'" for k in RateLimitKind)


class RateLimitEvent(Base):
    """回数制限の対象になる操作1回（database.md 3-7）。"""

    __tablename__ = "rate_limit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    kind: Mapped[str]
    # 接続元の IP か、利用者の ID（UUID を文字にしたもの）
    subject: Mapped[str]
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        CheckConstraint(f"kind IN ({_kind_values})", name="kind_valid"),
        # 制限の種類と人で絞り、「直近◯分」を数える（database.md 4-2 の 6）
        Index("ix_rate_limit_events_kind_subject_occurred_at", "kind", "subject", "occurred_at"),
    )
