import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.insight import INSIGHT_BODY_MAX_CHARS, INSIGHT_QUOTE_MAX_CHARS

QUESTION_MAX_CHARS = 200
ANSWER_MAX_CHARS = 500
PLANS_MAX = 3
RETRY_MAX = 3


class ProposalStatus(StrEnum):
    """AI提案の状態（database.md 3-4）。データベースでは6つ。"""

    GENERATING_QUESTION = "generating_question"
    AWAITING_ANSWER = "awaiting_answer"
    GENERATING_PLANS = "generating_plans"
    COMPLETED = "completed"
    QUESTION_FAILED = "question_failed"
    RETRY_LIMIT_REACHED = "retry_limit_reached"


_status_values = ", ".join(f"'{s.value}'" for s in ProposalStatus)


class AiProposal(Base):
    """AI提案（database.md 3-4）。

    テーブルは機能3で作る（気づきの詳細・本ごとの気づき一覧が、次の一歩の数や処理中かを返すため）。
    API は機能4で作る。
    """

    __tablename__ = "ai_proposals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    insight_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("insights.id", ondelete="CASCADE"))
    status: Mapped[str]
    insight_body: Mapped[str]
    insight_quote: Mapped[str | None]
    question: Mapped[str | None]
    answer: Mapped[str | None]
    # 次の一歩（行動プラン）。API と同じ形 [{"text": "…"}, …] で持つ
    plans: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    retry_count: Mapped[int] = mapped_column(server_default=text("0"))
    idempotency_key: Mapped[uuid.UUID]
    # 回数を数えた日（日本時間）
    usage_date: Mapped[date]
    status_changed_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        CheckConstraint(f"status IN ({_status_values})", name="status_valid"),
        CheckConstraint(
            f"char_length(insight_body) <= {INSIGHT_BODY_MAX_CHARS * 4}", name="insight_body_max_length"
        ),
        CheckConstraint(
            f"char_length(insight_quote) <= {INSIGHT_QUOTE_MAX_CHARS * 4}", name="insight_quote_max_length"
        ),
        CheckConstraint(f"char_length(question) <= {QUESTION_MAX_CHARS * 4}", name="question_max_length"),
        CheckConstraint(f"char_length(answer) <= {ANSWER_MAX_CHARS * 4}", name="answer_max_length"),
        CheckConstraint(
            f"plans IS NULL OR (jsonb_typeof(plans) = 'array' AND jsonb_array_length(plans) BETWEEN 1 AND {PLANS_MAX})",
            name="plans_shape",
        ),
        CheckConstraint(f"retry_count BETWEEN 0 AND {RETRY_MAX}", name="retry_count_range"),
        # 完了なら次の一歩と完了日時が必ずあり、完了でなければどちらもない
        CheckConstraint(
            "(status = 'completed') = (plans IS NOT NULL AND completed_at IS NOT NULL)",
            name="completed_has_plans",
        ),
        UniqueConstraint("user_id", "idempotency_key", name="uq_ai_proposals_user_id_idempotency_key"),
        # 1つの気づきに完了したAI提案は1件まで（部分ユニークインデックス）
        Index(
            "ai_proposals_one_completed_per_insight",
            "insight_id",
            unique=True,
            postgresql_where=text("status = 'completed'"),
        ),
        # この気づきのAI提案を探す（database.md 4-2 の 4）
        Index("ix_ai_proposals_insight_id", "insight_id"),
        # 後片付け（database.md 4-2 の 5）
        Index("ix_ai_proposals_status_status_changed_at", "status", "status_changed_at"),
    )
