import uuid
from datetime import date

from sqlalchemy import CheckConstraint, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

DAILY_LIMIT = 5
APP_DAILY_LIMIT = 100


class AiUsage(Base):
    """ある利用者の、ある日（日本時間）の AI の利用回数（database.md 3-5）。1日1行。"""

    __tablename__ = "ai_usages"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    usage_date: Mapped[date] = mapped_column(primary_key=True)
    used_count: Mapped[int] = mapped_column(server_default=text("0"))

    __table_args__ = (CheckConstraint(f"used_count BETWEEN 0 AND {DAILY_LIMIT}", name="used_count_range"),)


class AppAiUsage(Base):
    """アプリ全体の、ある日（日本時間）の AI の利用回数（database.md 3-6）。誰が使ったかは持たない。"""

    __tablename__ = "app_ai_usages"

    usage_date: Mapped[date] = mapped_column(primary_key=True)
    used_count: Mapped[int] = mapped_column(server_default=text("0"))

    __table_args__ = (CheckConstraint(f"used_count BETWEEN 0 AND {APP_DAILY_LIMIT}", name="used_count_range"),)
