"""気づき一覧・本ごとの気づき一覧・気づき（api.md 7-4・7-5）。

どの処理も、まず「自分の気づき・自分の本か」で絞る（他人のものは 404）。
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ColumnElement,
    Select,
    and_,
    case,
    delete,
    exists,
    func,
    literal,
    or_,
    select,
    tuple_,
    update,
)
from sqlalchemy.dialects.postgresql import aggregate_order_by, array_agg
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.cursor import decode_cursor, encode_cursor, invalid_cursor
from app.core.errors import AppError
from app.models import AiProposal, Book, Insight, ProposalStatus
from app.schemas.insight import (
    GroupSort,
    InsightBook,
    InsightCard,
    InsightDetail,
    InsightGroup,
    InsightGroupDetail,
    LatestProposal,
    PendingProposal,
    Plan,
)
from app.services.books import book_not_found

GROUP_PAGE_SIZE = 30
CARD_PAGE_SIZE = 20

# 値がない日時を「とても古い日時」に置き換えて比べる（NULLS LAST と同じ並びになる）
_VERY_OLD = literal(datetime.fromisoformat("0001-01-01T00:00:00+00:00"))


def insight_not_found() -> AppError:
    return AppError(404, "INSIGHT_NOT_FOUND", "気づきが見つかりません")


def group_not_found() -> AppError:
    return AppError(404, "INSIGHT_GROUP_NOT_FOUND", "気づきのまとまりが見つかりません")


# ---- 気づきのまとまり（api.md 7-4 の前提） ----


def _groups_query(user_id: uuid.UUID):
    """自分の気づきを元の本でまとめたものと、気づき0件の自分の本棚の本を合わせた表。"""
    agg = (
        select(
            Insight.original_book_id.label("id"),
            func.count().label("insight_count"),
            func.max(Insight.created_at).label("last_written_at"),
            # 題名・著者・表紙は、いちばん新しい気づきの写しから取る（本がある間はどの写しも同じ値）
            array_agg(aggregate_order_by(Insight.book_title, Insight.created_at.desc()))[1].label("title"),
            array_agg(aggregate_order_by(Insight.book_author, Insight.created_at.desc()))[1].label("author"),
            array_agg(aggregate_order_by(Insight.book_cover_url, Insight.created_at.desc()))[1].label("cover_url"),
        )
        .where(Insight.user_id == user_id)
        .group_by(Insight.original_book_id)
        .subquery("agg")
    )
    my_books = select(Book).where(Book.user_id == user_id).subquery("my_books")

    has_insights = agg.c.id.is_not(None)
    groups = (
        select(
            func.coalesce(agg.c.id, my_books.c.id).label("id"),
            func.coalesce(agg.c.insight_count, 0).label("insight_count"),
            agg.c.last_written_at,
            my_books.c.created_at.label("registered_at"),
            case((has_insights, agg.c.title), else_=my_books.c.title).label("title"),
            case((has_insights, agg.c.author), else_=my_books.c.author).label("author"),
            case((has_insights, agg.c.cover_url), else_=my_books.c.cover_url).label("cover_url"),
            my_books.c.id.is_(None).label("deleted"),
        )
        .select_from(agg)
        .join(my_books, agg.c.id == my_books.c.id, full=True)
        .subquery("groups")
    )
    return groups


def _sort_keys(groups, sort: GroupSort) -> list[ColumnElement[Any]]:
    """並べ方の表（api.md 7-4）の値。どれも「大きいほど先」にそろえ、まとめて降順で比べる。"""
    last = func.coalesce(groups.c.last_written_at, _VERY_OLD)
    registered = func.coalesce(groups.c.registered_at, _VERY_OLD)
    count = groups.c.insight_count
    if sort is GroupSort.RECENT:
        return [last, registered]
    if sort is GroupSort.MANY:
        return [count, last, registered]
    # few は件数の少ない順なので、符号を逆にして「大きいほど先」にそろえる
    return [-count, registered, last]


def _key_values(row: Any, sort: GroupSort) -> list[Any]:
    last = row.last_written_at.isoformat() if row.last_written_at else None
    registered = row.registered_at.isoformat() if row.registered_at else None
    if sort is GroupSort.RECENT:
        return [last, registered]
    if sort is GroupSort.MANY:
        return [row.insight_count, last, registered]
    return [-row.insight_count, registered, last]


def _parse_group_cursor(cursor: str, sort: GroupSort) -> tuple[list[Any], uuid.UUID]:
    data = decode_cursor(cursor)
    if data.get("sort") != sort.value:
        # 目印の意味が合わないので断る（api.md 7-4）
        raise invalid_cursor()
    try:
        keys = data["k"]
        group_id = uuid.UUID(data["i"])
        expected = 2 if sort is GroupSort.RECENT else 3
        if not isinstance(keys, list) or len(keys) != expected:
            raise ValueError
        values: list[Any] = []
        for index, value in enumerate(keys):
            is_count = sort is not GroupSort.RECENT and index == 0
            if is_count:
                if not isinstance(value, int):
                    raise ValueError
                values.append(value)
            else:
                values.append(datetime.fromisoformat(value) if value is not None else None)
        return values, group_id
    except (KeyError, TypeError, ValueError):
        raise invalid_cursor() from None


def list_groups(db: Session, user_id: uuid.UUID, sort: GroupSort, cursor: str | None) -> tuple[list[InsightGroup], str | None]:
    groups = _groups_query(user_id)
    keys = _sort_keys(groups, sort)
    query: Select[Any] = select(groups)

    if cursor is not None:
        values, group_id = _parse_group_cursor(cursor, sort)
        # 値がない日時は、並べるときと同じく「とても古い日時」として比べる
        compare = [literal(v) if v is not None else _VERY_OLD for v in values]
        query = query.where(tuple_(*keys, groups.c.id) < tuple_(*compare, literal(group_id)))

    rows = db.execute(
        query.order_by(*[k.desc() for k in keys], groups.c.id.desc()).limit(GROUP_PAGE_SIZE + 1)
    ).all()

    next_cursor = None
    if len(rows) > GROUP_PAGE_SIZE:
        rows = rows[:GROUP_PAGE_SIZE]
        last_row = rows[-1]
        next_cursor = encode_cursor({"sort": sort.value, "k": _key_values(last_row, sort), "i": str(last_row.id)})

    items = [
        InsightGroup(
            id=row.id,
            title=row.title,
            cover_url=row.cover_url,
            insight_count=row.insight_count,
            last_written_at=row.last_written_at,
            deleted=row.deleted,
        )
        for row in rows
    ]
    return items, next_cursor


def get_group(db: Session, user_id: uuid.UUID, group_id: uuid.UUID) -> InsightGroupDetail:
    groups = _groups_query(user_id)
    row = db.execute(select(groups).where(groups.c.id == group_id)).one_or_none()
    if row is None:
        raise group_not_found()
    return InsightGroupDetail(
        id=row.id,
        title=row.title,
        author=row.author,
        cover_url=row.cover_url,
        insight_count=row.insight_count,
        last_written_at=row.last_written_at,
        deleted=row.deleted,
    )


def _group_exists(db: Session, user_id: uuid.UUID, group_id: uuid.UUID) -> bool:
    return bool(
        db.scalar(
            select(
                or_(
                    exists().where(Book.id == group_id, Book.user_id == user_id),
                    exists().where(Insight.original_book_id == group_id, Insight.user_id == user_id),
                )
            )
        )
    )


def list_group_insights(
    db: Session, user_id: uuid.UUID, group_id: uuid.UUID, cursor: str | None
) -> tuple[list[InsightCard], str | None]:
    if not _group_exists(db, user_id, group_id):
        raise group_not_found()

    # 次の一歩の数：完了したAI提案は1つの気づきに1件だけなので、それを外部結合して1回で数える（N＋1 にしない）
    completed = (
        select(AiProposal.insight_id, func.jsonb_array_length(AiProposal.plans).label("plan_count"))
        .where(AiProposal.status == ProposalStatus.COMPLETED, AiProposal.user_id == user_id)
        .subquery("completed")
    )
    query = (
        select(Insight, func.coalesce(completed.c.plan_count, 0).label("next_step_count"))
        .outerjoin(completed, completed.c.insight_id == Insight.id)
        .where(Insight.user_id == user_id, Insight.original_book_id == group_id)
    )
    if cursor is not None:
        data = decode_cursor(cursor)
        try:
            created_at = datetime.fromisoformat(data["c"])
            insight_id = uuid.UUID(data["i"])
        except (KeyError, TypeError, ValueError):
            raise invalid_cursor() from None
        query = query.where(tuple_(Insight.created_at, Insight.id) < tuple_(created_at, insight_id))

    rows = db.execute(
        query.order_by(Insight.created_at.desc(), Insight.id.desc()).limit(CARD_PAGE_SIZE + 1)
    ).all()

    next_cursor = None
    if len(rows) > CARD_PAGE_SIZE:
        rows = rows[:CARD_PAGE_SIZE]
        last = rows[-1][0]
        next_cursor = encode_cursor({"c": last.created_at.isoformat(), "i": str(last.id)})

    items = [
        InsightCard(
            id=insight.id,
            page=insight.page,
            quote=insight.quote,
            body=insight.body,
            next_step_count=count,
            created_at=insight.created_at,
        )
        for insight, count in rows
    ]
    return items, next_cursor


# ---- 気づき（api.md 7-5） ----


def create_insight(
    db: Session,
    user_id: uuid.UUID,
    *,
    book_id: uuid.UUID,
    page: int | None,
    quote: str | None,
    body: str,
) -> uuid.UUID:
    book = db.scalars(select(Book).where(Book.id == book_id, Book.user_id == user_id)).one_or_none()
    if book is None:
        raise book_not_found()

    # 題名・著者・表紙の写しは画面から受け取らず、本から作る（書き換えを防ぐため）
    insight = Insight(
        user_id=user_id,
        book_id=book.id,
        original_book_id=book.id,
        book_title=book.title,
        book_author=book.author,
        book_cover_url=book.cover_url,
        page=page,
        quote=quote,
        body=body,
    )
    db.add(insight)
    try:
        db.commit()
    except IntegrityError:
        # 本を探してから保存するまでの間に、別の端末で本が削除された（外部キーで断られる）
        db.rollback()
        raise book_not_found() from None
    return insight.id


def get_insight(db: Session, user_id: uuid.UUID, insight_id: uuid.UUID) -> InsightDetail:
    insight = db.scalars(
        select(Insight).where(Insight.id == insight_id, Insight.user_id == user_id)
    ).one_or_none()
    if insight is None:
        raise insight_not_found()

    latest = db.scalars(
        select(AiProposal).where(
            AiProposal.insight_id == insight.id, AiProposal.status == ProposalStatus.COMPLETED
        )
    ).one_or_none()

    # まだ終わっていないAI提案：作成中（深掘り・行動プラン）か、回答が入った回答待ち（行動プランの作成に失敗）
    pending = db.scalars(
        select(AiProposal)
        .where(
            AiProposal.insight_id == insight.id,
            or_(
                AiProposal.status.in_(
                    [ProposalStatus.GENERATING_QUESTION, ProposalStatus.GENERATING_PLANS]
                ),
                and_(AiProposal.status == ProposalStatus.AWAITING_ANSWER, AiProposal.answer.is_not(None)),
            ),
        )
        .order_by(AiProposal.created_at.desc())
        .limit(1)
    ).one_or_none()

    return InsightDetail(
        id=insight.id,
        page=insight.page,
        quote=insight.quote,
        body=insight.body,
        created_at=insight.created_at,
        book=InsightBook(
            id=insight.original_book_id,
            title=insight.book_title,
            author=insight.book_author,
            cover_url=insight.book_cover_url,
        ),
        latest_proposal=(
            LatestProposal(
                id=latest.id,
                completed_at=latest.completed_at,
                plans=[Plan(text=p["text"]) for p in latest.plans or []],
            )
            if latest is not None and latest.completed_at is not None
            else None
        ),
        pending_proposal=(
            PendingProposal(
                id=pending.id,
                status="failed" if pending.status == ProposalStatus.AWAITING_ANSWER else "processing",
            )
            if pending is not None
            else None
        ),
    )


def update_insight(db: Session, user_id: uuid.UUID, insight_id: uuid.UUID, changes: dict[str, Any]) -> None:
    """送られた項目だけ書き換える。本があるかは確かめない（削除した本の気づきも編集できる）。"""
    statement = update(Insight).where(Insight.id == insight_id, Insight.user_id == user_id)
    if changes:
        statement = statement.values(**changes)
    else:
        # 何も送られていなくても、自分の気づきかは確かめる
        statement = statement.values(id=Insight.id)
    updated = db.scalar(statement.returning(Insight.id))
    if updated is None:
        db.rollback()
        raise insight_not_found()
    db.commit()


def delete_insight(db: Session, user_id: uuid.UUID, insight_id: uuid.UUID) -> None:
    # その気づきのAI提案もまとめて消える（ON DELETE CASCADE）
    deleted = db.scalar(
        delete(Insight).where(Insight.id == insight_id, Insight.user_id == user_id).returning(Insight.id)
    )
    if deleted is None:
        db.rollback()
        raise insight_not_found()
    db.commit()
