"""AI提案（api.md 2章・7-6、notes.md 2章）。

回数や状態が二重に変わらないよう、「確かめる → 変える」はどれもデータベースへの1回の命令
（条件付きの UPDATE・DELETE・UPSERT）か、行のロックの中で行う。
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, exists, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import AppError
from app.db import SessionLocal
from app.models import AiProposal, AiUsage, AppAiUsage, Insight, ProposalStatus, RateLimitEvent, User, UserAttribute
from app.models.ai_proposal import RETRY_MAX
from app.models.ai_usage import APP_DAILY_LIMIT, DAILY_LIMIT
from app.services.ai_client import AiClient, AiError, InsightContext, call_with_retry

logger = logging.getLogger(__name__)

STUCK_AFTER = timedelta(minutes=2)
EXPIRE_AFTER = timedelta(hours=24)

S = ProposalStatus


def proposal_not_found() -> AppError:
    return AppError(404, "AI_PROPOSAL_NOT_FOUND", "AI提案が見つかりません")


def state_conflict() -> AppError:
    return AppError(409, "AI_PROPOSAL_STATE_CONFLICT", "AI提案の状態が変わっています。最新の状態を表示します。")


# ---- 回数（database.md 3-5・3-6） ----


def _reserve_usage(db: Session, user_id: uuid.UUID, today: date) -> None:
    """個人とアプリ全体の回数を、同じトランザクションの中で1回ずつ増やす。上限なら断る（どちらも増やさない）。"""
    personal = db.scalar(
        insert(AiUsage)
        .values(user_id=user_id, usage_date=today, used_count=1)
        .on_conflict_do_update(
            index_elements=[AiUsage.user_id, AiUsage.usage_date],
            set_={"used_count": AiUsage.used_count + 1},
            where=AiUsage.used_count < DAILY_LIMIT,
        )
        .returning(AiUsage.used_count)
    )
    if personal is None:
        db.rollback()
        raise AppError(429, "AI_DAILY_LIMIT", "本日の AI提案の回数を使い切っています")
    app_count = db.scalar(
        insert(AppAiUsage)
        .values(usage_date=today, used_count=1)
        .on_conflict_do_update(
            index_elements=[AppAiUsage.usage_date],
            set_={"used_count": AppAiUsage.used_count + 1},
            where=AppAiUsage.used_count < APP_DAILY_LIMIT,
        )
        .returning(AppAiUsage.used_count)
    )
    if app_count is None:
        # 個人の +1 も一緒に取り消す
        db.rollback()
        logger.warning("app-wide ai limit reached")
        raise AppError(429, "AI_APP_LIMIT", "本日はアプリ全体の AI提案の受付を終了しました")


def _release_usage(db: Session, user_id: uuid.UUID, usage_date: date, *, app: bool) -> None:
    """回数を1つ戻す。+1 した日（AI提案の usage_date）の行を戻す。"""
    db.execute(
        update(AiUsage)
        .where(AiUsage.user_id == user_id, AiUsage.usage_date == usage_date, AiUsage.used_count > 0)
        .values(used_count=AiUsage.used_count - 1)
    )
    if app:
        db.execute(
            update(AppAiUsage)
            .where(AppAiUsage.usage_date == usage_date, AppAiUsage.used_count > 0)
            .values(used_count=AppAiUsage.used_count - 1)
        )


# ---- 止まったAI提案の片付け（api.md 2-8） ----


@dataclass
class CleanupResult:
    question_failed: int = 0
    plans_reset: int = 0
    retry_limit: int = 0
    deleted: int = 0


def cleanup(db: Session, now: datetime, *, user_id: uuid.UUID | None = None, insight_id: uuid.UUID | None = None,
            proposal_id: uuid.UUID | None = None) -> CleanupResult:
    """止まったAI提案を片付ける。その場の判定（user_id などで絞る）と、5分おきの片付け（絞らない）の両方から呼ぶ。

    どの片付けも「まだその状態なら変える」という条件付きの命令なので、同時に動いても回数を2回戻さない。
    """
    scope = []
    if user_id is not None:
        scope.append(AiProposal.user_id == user_id)
    if insight_id is not None:
        scope.append(AiProposal.insight_id == insight_id)
    if proposal_id is not None:
        scope.append(AiProposal.id == proposal_id)
    stuck = AiProposal.status_changed_at < now - STUCK_AFTER
    expired = AiProposal.status_changed_at < now - EXPIRE_AFTER
    result = CleanupResult()

    # 深掘りの作成中のまま2分 → question_failed にし、個人とアプリ全体の回数を戻す
    rows = db.execute(
        update(AiProposal)
        .where(AiProposal.status == S.GENERATING_QUESTION, stuck, *scope)
        .values(status=S.QUESTION_FAILED, status_changed_at=now)
        .returning(AiProposal.user_id, AiProposal.usage_date)
    ).all()
    for owner, usage_date in rows:
        _release_usage(db, owner, usage_date, app=True)
    result.question_failed = len(rows)

    # 行動プランの作成中のまま2分 → 送り直しが残っていれば回答待ち（plan_failed）に戻す
    result.plans_reset = len(
        db.execute(
            update(AiProposal)
            .where(AiProposal.status == S.GENERATING_PLANS, AiProposal.retry_count < RETRY_MAX, stuck, *scope)
            .values(status=S.AWAITING_ANSWER, status_changed_at=now)
            .returning(AiProposal.id)
        ).all()
    )
    # 4回目の送信で止まった → retry_limit_reached にし、本人の回数を1回戻す（AI が失敗した4回目と同じ）
    rows = db.execute(
        update(AiProposal)
        .where(AiProposal.status == S.GENERATING_PLANS, AiProposal.retry_count >= RETRY_MAX, stuck, *scope)
        .values(status=S.RETRY_LIMIT_REACHED, status_changed_at=now)
        .returning(AiProposal.user_id, AiProposal.usage_date)
    ).all()
    for owner, usage_date in rows:
        _release_usage(db, owner, usage_date, app=False)
    result.retry_limit = len(rows)

    # 回答待ち・失敗して終わったもののまま24時間 → 削除する（回数は戻さない／失敗したときに戻し済み）
    result.deleted = len(
        db.execute(
            delete(AiProposal)
            .where(
                AiProposal.status.in_([S.AWAITING_ANSWER, S.QUESTION_FAILED, S.RETRY_LIMIT_REACHED]),
                expired,
                *scope,
            )
            .returning(AiProposal.id)
        ).all()
    )
    db.commit()
    return result


# ---- 始める（api.md 2-4・7-6） ----


def start(db: Session, user_id: uuid.UUID, insight_id: uuid.UUID, idempotency_key: uuid.UUID) -> tuple[uuid.UUID, bool]:
    """AI提案を作り、(AI提案の ID, 深掘りを作り始める必要があるか) を返す。"""
    now = clock.now()
    cleanup(db, now, insight_id=insight_id, user_id=user_id)

    # 同じ気づきへの開始を1つずつ順番に通す（「処理中か確かめる → 作る」の間に割り込ませない）
    insight = db.scalars(
        select(Insight).where(Insight.id == insight_id, Insight.user_id == user_id).with_for_update()
    ).one_or_none()
    if insight is None:
        db.rollback()
        raise AppError(404, "INSIGHT_NOT_FOUND", "気づきが見つかりません")

    # 同じ受付番号で作ったものがあれば、回数を増やさずにそれを返す（送り直し）
    existing = db.scalar(
        select(AiProposal.id).where(AiProposal.user_id == user_id, AiProposal.idempotency_key == idempotency_key)
    )
    if existing is not None:
        db.rollback()
        return existing, False

    in_progress = db.scalar(
        select(
            exists().where(
                AiProposal.insight_id == insight_id,
                AiProposal.status.in_([S.GENERATING_QUESTION, S.GENERATING_PLANS]),
            )
        )
    )
    if in_progress:
        db.rollback()
        raise AppError(409, "AI_PROPOSAL_IN_PROGRESS", "この気づきの AI提案を処理中です")

    today = clock.jst_date(now)
    _reserve_usage(db, user_id, today)

    # 回答待ちのもの・失敗して終わったものは、新しく始めるときに消す
    db.execute(
        delete(AiProposal).where(
            AiProposal.insight_id == insight_id,
            AiProposal.status.in_([S.AWAITING_ANSWER, S.QUESTION_FAILED, S.RETRY_LIMIT_REACHED]),
        )
    )
    proposal = AiProposal(
        user_id=user_id,
        insight_id=insight_id,
        status=S.GENERATING_QUESTION,
        # 始めた時点の気づきの写し（途中で気づきを編集しても、深掘りと前提が食い違わないように）
        insight_body=insight.body,
        insight_quote=insight.quote,
        idempotency_key=idempotency_key,
        usage_date=today,
        status_changed_at=now,
    )
    db.add(proposal)
    try:
        db.commit()
    except IntegrityError:
        # ほぼ同時に同じ受付番号が届いた（別の気づきに対してなど）。既にあるものとして返す
        db.rollback()
        existing = db.scalar(
            select(AiProposal.id).where(AiProposal.user_id == user_id, AiProposal.idempotency_key == idempotency_key)
        )
        if existing is None:
            raise
        return existing, False
    return proposal.id, True


# ---- 裏で AI を呼ぶ（BackgroundTasks） ----


def _context(db: Session, proposal: AiProposal) -> InsightContext:
    insight = db.get(Insight, proposal.insight_id)
    user = db.get(User, proposal.user_id)
    assert insight is not None and user is not None
    return InsightContext(
        attribute=UserAttribute(user.attribute).label,
        book_title=insight.book_title,
        book_author=insight.book_author,
        quote=proposal.insight_quote,
        body=proposal.insight_body,
    )


def run_question(proposal_id: uuid.UUID, ai: AiClient) -> None:
    """深掘りを作る。保存も失敗の扱いも「まだ深掘りの作成中なら」の条件付き（途中で終了・削除されていたら捨てる）。"""
    with SessionLocal() as db:
        proposal = db.get(AiProposal, proposal_id)
        if proposal is None or proposal.status != S.GENERATING_QUESTION:
            return
        context = _context(db, proposal)
        db.rollback()

        try:
            question = call_with_retry(lambda: ai.generate_question(context))
        except AiError as error:
            logger.warning("question generation failed: proposal=%s reason=%s", proposal_id, error.reason)
            row = db.execute(
                update(AiProposal)
                .where(AiProposal.id == proposal_id, AiProposal.status == S.GENERATING_QUESTION)
                .values(status=S.QUESTION_FAILED, status_changed_at=clock.now())
                .returning(AiProposal.user_id, AiProposal.usage_date)
            ).one_or_none()
            if row is not None:
                # 深掘りの作成に失敗したら、個人とアプリ全体の回数を戻す
                _release_usage(db, row.user_id, row.usage_date, app=True)
            db.commit()
            return

        result = db.execute(
            update(AiProposal)
            .where(AiProposal.id == proposal_id, AiProposal.status == S.GENERATING_QUESTION)
            .values(status=S.AWAITING_ANSWER, question=question, status_changed_at=clock.now())
        )
        if result.rowcount == 0:
            logger.info("proposal %s was ended or removed; discarding the question", proposal_id)
        db.commit()


def run_plans(proposal_id: uuid.UUID, ai: AiClient) -> None:
    """次の一歩を作る。保存も失敗の扱いも「まだ行動プランの作成中なら」の条件付き。"""
    with SessionLocal() as db:
        proposal = db.get(AiProposal, proposal_id)
        if proposal is None or proposal.status != S.GENERATING_PLANS:
            return
        context = _context(db, proposal)
        question, answer = proposal.question or "", proposal.answer or ""
        db.rollback()

        try:
            plans = call_with_retry(lambda: ai.generate_plans(context, question, answer))
        except AiError as error:
            logger.warning("plan generation failed: proposal=%s reason=%s", proposal_id, error.reason)
            _plans_failed(db, proposal_id)
            return

        now = clock.now()
        # この AI提案がまだ行動プランの作成中か、行をロックして確かめる
        locked = db.scalars(
            select(AiProposal)
            .where(AiProposal.id == proposal_id, AiProposal.status == S.GENERATING_PLANS)
            .with_for_update()
        ).one_or_none()
        if locked is None:
            logger.info("proposal %s was removed or changed; discarding the plans", proposal_id)
            db.rollback()
            return
        # 前の完了したAI提案を消してから、完了にする（1つのトランザクション。1つの気づきに完了は1件だけ）
        db.execute(
            delete(AiProposal).where(
                AiProposal.insight_id == locked.insight_id,
                AiProposal.status == S.COMPLETED,
                AiProposal.id != proposal_id,
            )
        )
        locked.status = S.COMPLETED
        locked.plans = [{"text": text} for text in plans]
        locked.completed_at = now
        locked.status_changed_at = now
        db.commit()


def _plans_failed(db: Session, proposal_id: uuid.UUID) -> None:
    now = clock.now()
    # 送り直しが残っていれば回答待ちに戻す（画面では plan_failed）
    reset = db.execute(
        update(AiProposal)
        .where(
            AiProposal.id == proposal_id,
            AiProposal.status == S.GENERATING_PLANS,
            AiProposal.retry_count < RETRY_MAX,
        )
        .values(status=S.AWAITING_ANSWER, status_changed_at=now)
    )
    if reset.rowcount == 0:
        # 最初の送信と送り直し3回の、4回目の失敗 → 終了にし、本人の回数を1回戻す（アプリ全体は戻さない）
        row = db.execute(
            update(AiProposal)
            .where(
                AiProposal.id == proposal_id,
                AiProposal.status == S.GENERATING_PLANS,
                AiProposal.retry_count >= RETRY_MAX,
            )
            .values(status=S.RETRY_LIMIT_REACHED, status_changed_at=now)
            .returning(AiProposal.user_id, AiProposal.usage_date)
        ).one_or_none()
        if row is not None:
            _release_usage(db, row.user_id, row.usage_date, app=False)
    db.commit()


# ---- 取得（api.md 7-6） ----


def api_status(proposal: AiProposal) -> str:
    """データベースの6つの状態を、画面の場面に合わせた7つの値に直す。"""
    if proposal.status == S.AWAITING_ANSWER:
        return "plan_failed" if proposal.answer is not None else "awaiting_answer"
    return proposal.status


def get(db: Session, user_id: uuid.UUID, proposal_id: uuid.UUID) -> dict[str, Any]:
    cleanup(db, clock.now(), user_id=user_id, proposal_id=proposal_id)
    row = db.execute(
        select(AiProposal, Insight)
        .join(Insight, Insight.id == AiProposal.insight_id)
        .where(AiProposal.id == proposal_id, AiProposal.user_id == user_id)
    ).one_or_none()
    if row is None:
        raise proposal_not_found()
    proposal, insight = row
    return {
        "id": proposal.id,
        "status": api_status(proposal),
        "insight_id": proposal.insight_id,
        "insight": {
            # 引用・本文は始めた時点の写し。本の題名とページは元の気づきから取る
            "book_title": insight.book_title,
            "page": insight.page,
            "quote": proposal.insight_quote,
            "body": proposal.insight_body,
        },
        "question": proposal.question,
        "answer": proposal.answer,
        "plans": proposal.plans,
        "completed_at": proposal.completed_at,
        "retries_left": RETRY_MAX - proposal.retry_count,
    }


# ---- 回答・送り直し・途中でやめる ----


def _conflict_or_not_found(db: Session, user_id: uuid.UUID, proposal_id: uuid.UUID) -> AppError:
    """条件付きの命令で書き換えた行が0件のとき：行があれば 409、なければ 404。"""
    db.rollback()
    found = db.scalar(select(AiProposal.id).where(AiProposal.id == proposal_id, AiProposal.user_id == user_id))
    return state_conflict() if found is not None else proposal_not_found()


def answer(db: Session, user_id: uuid.UUID, proposal_id: uuid.UUID, answer_text: str) -> None:
    now = clock.now()
    # 回答待ちのまま24時間を過ぎていれば、削除がまだでもその場で消して 404（2-8）
    db.execute(
        delete(AiProposal).where(
            AiProposal.id == proposal_id,
            AiProposal.user_id == user_id,
            AiProposal.status == S.AWAITING_ANSWER,
            AiProposal.status_changed_at < now - EXPIRE_AFTER,
        )
    )
    db.commit()
    changed = db.execute(
        update(AiProposal)
        .where(
            AiProposal.id == proposal_id,
            AiProposal.user_id == user_id,
            AiProposal.status == S.AWAITING_ANSWER,
            AiProposal.answer.is_(None),
        )
        .values(status=S.GENERATING_PLANS, answer=answer_text, status_changed_at=now)
    )
    if changed.rowcount == 0:
        raise _conflict_or_not_found(db, user_id, proposal_id)
    db.commit()


def retry(db: Session, user_id: uuid.UUID, proposal_id: uuid.UUID, answer_text: str) -> None:
    # 「plan_failed で、送り直しが3回未満なら +1」を1回の命令で（連打や2つのタブでも1回だけ）
    changed = db.execute(
        update(AiProposal)
        .where(
            AiProposal.id == proposal_id,
            AiProposal.user_id == user_id,
            AiProposal.status == S.AWAITING_ANSWER,
            AiProposal.answer.is_not(None),
            AiProposal.retry_count < RETRY_MAX,
        )
        .values(
            status=S.GENERATING_PLANS,
            answer=answer_text,
            retry_count=AiProposal.retry_count + 1,
            status_changed_at=clock.now(),
        )
    )
    if changed.rowcount == 0:
        raise _conflict_or_not_found(db, user_id, proposal_id)
    db.commit()


def abandon(db: Session, user_id: uuid.UUID, proposal_id: uuid.UUID) -> None:
    # 回答を送る前（深掘りの作成中・回答待ち・plan_failed）だけ消す。回数は戻さない
    deleted = db.scalar(
        delete(AiProposal)
        .where(
            AiProposal.id == proposal_id,
            AiProposal.user_id == user_id,
            AiProposal.status.in_([S.GENERATING_QUESTION, S.AWAITING_ANSWER]),
        )
        .returning(AiProposal.id)
    )
    if deleted is None:
        raise _conflict_or_not_found(db, user_id, proposal_id)
    db.commit()


# ---- 本日の残り回数（api.md 7-2） ----


def usage(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    now = clock.now()
    # 止まったAI提案を先に片付けてから数える（戻るはずの回数が減ったまま表示されないように）
    cleanup(db, now, user_id=user_id)
    today = clock.jst_date(now)
    used = db.scalar(select(AiUsage.used_count).where(AiUsage.user_id == user_id, AiUsage.usage_date == today)) or 0
    app_used = db.scalar(select(AppAiUsage.used_count).where(AppAiUsage.usage_date == today)) or 0
    return {
        "remaining_today": max(0, DAILY_LIMIT - used),
        "daily_limit": DAILY_LIMIT,
        "app_limit_reached": app_used >= APP_DAILY_LIMIT,
    }


# ---- 回数制限の記録の片付け（api.md 5-2。接続元の IP は1日で消す） ----


def cleanup_rate_limit_events(db: Session, now: datetime) -> int:
    deleted = db.execute(
        delete(RateLimitEvent).where(RateLimitEvent.occurred_at < now - timedelta(days=1)).returning(RateLimitEvent.id)
    ).all()
    db.commit()
    return len(deleted)

