import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, false, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserAttribute(StrEnum):
    """属性（api.md 7-1）。入力の確認・保存・AI に送るときの変換で、この1か所の定義を使う。"""

    HIGH_SCHOOL = "high_school"
    UNIVERSITY = "university"
    WORKING = "working"
    HOMEMAKER = "homemaker"
    OTHER = "other"

    @property
    def label(self) -> str:
        """AI に送るときの日本語（api.md 7-1。AI が読みやすいように直して送る）"""
        return _ATTRIBUTE_LABELS[self]


_ATTRIBUTE_LABELS = {
    UserAttribute.HIGH_SCHOOL: "高校生",
    UserAttribute.UNIVERSITY: "大学生・専門学生",
    UserAttribute.WORKING: "社会人",
    UserAttribute.HOMEMAKER: "主婦・主夫",
    UserAttribute.OTHER: "その他",
}


EMAIL_MAX_CHARS = 254

_attribute_values = ", ".join(f"'{a.value}'" for a in UserAttribute)


class User(Base):
    """利用者（database.md 3-1）。"""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    email: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]
    attribute: Mapped[str]
    email_verified: Mapped[bool] = mapped_column(server_default=false())
    token_version: Mapped[int] = mapped_column(server_default=text("0"))
    terms_agreed_at: Mapped[datetime]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        CheckConstraint("email = lower(email) AND email <> ''", name="email_normalized"),
        CheckConstraint(f"char_length(email) <= {EMAIL_MAX_CHARS * 4}", name="email_max_length"),
        CheckConstraint(f"attribute IN ({_attribute_values})", name="attribute_valid"),
    )
