"""回数制限の部品（api.md 5-2）。ログイン・新規登録・本の検索・パスワードの再確認の4つで使い回す。

数え方：今から遡った時間の中の行を数える（スライディングウィンドウ）。

同時に押された場合の対策（notes.md 2章）：
「数える → 足す」の間に別のリクエストが割り込むと、どちらも「まだ4回」と数えて上限を超えてしまう。
そこで、同じ制限・同じ人のリクエストは、PostgreSQL のアドバイザリーロックで1つずつ順番に通す。
ロックはトランザクションの終わり（commit・rollback）で自動で外れる。
"""

import math
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import AppError
from app.models import RateLimitEvent, RateLimitKind


@dataclass(frozen=True)
class RateLimitRule:
    kind: RateLimitKind
    limit: int
    window: timedelta
    error_code: str


LOGIN = RateLimitRule(RateLimitKind.LOGIN, 5, timedelta(minutes=1), "LOGIN_RATE_LIMIT")
REGISTER = RateLimitRule(RateLimitKind.REGISTER, 5, timedelta(hours=1), "REGISTER_RATE_LIMIT")
SEARCH = RateLimitRule(RateLimitKind.SEARCH, 10, timedelta(minutes=1), "SEARCH_RATE_LIMIT")
PASSWORD_CONFIRM = RateLimitRule(
    RateLimitKind.PASSWORD_CONFIRM, 5, timedelta(hours=1), "PASSWORD_CONFIRM_RATE_LIMIT"
)


def reserve(db: Session, rule: RateLimitRule, subject: str) -> uuid.UUID:
    """上限に達していなければ1回分を記録して、その行の ID を返す。達していれば 429 で断る。

    「失敗だけ数える」制限（ログインなど）は、先にこの関数で1回分を押さえてから処理し、
    成功したら release() で取り消す。こうすると、同時に押されても上限を超えて試せない。
    """
    db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(f"{rule.kind}:{subject}", 0))))

    now = clock.now()
    count, oldest = db.execute(
        select(func.count(), func.min(RateLimitEvent.occurred_at)).where(
            RateLimitEvent.kind == rule.kind,
            RateLimitEvent.subject == subject,
            RateLimitEvent.occurred_at > now - rule.window,
        )
    ).one()

    if count >= rule.limit:
        db.rollback()  # ロックを外す
        retry_after = max(1, math.ceil((oldest + rule.window - now).total_seconds()))
        raise AppError(
            429,
            rule.error_code,
            "回数の上限に達しました",
            headers={"Retry-After": str(retry_after)},
        )

    event_id = db.execute(
        insert(RateLimitEvent)
        .values(kind=rule.kind, subject=subject, occurred_at=now)
        .returning(RateLimitEvent.id)
    ).scalar_one()
    db.commit()
    return event_id


def release(db: Session, event_id: uuid.UUID) -> None:
    """reserve() で押さえた1回分を取り消す（成功は数えない制限で、成功したとき）。"""
    db.execute(delete(RateLimitEvent).where(RateLimitEvent.id == event_id))
    db.commit()
