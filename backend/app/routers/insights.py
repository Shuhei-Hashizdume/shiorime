import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.dependencies import CurrentUser, DbSession
from app.schemas.insight import (
    CreatedInsight,
    GroupSort,
    InsightCardList,
    InsightCreate,
    InsightDetail,
    InsightGroupDetail,
    InsightGroupList,
    InsightUpdate,
)
from app.services import insights as insights_service

groups_router = APIRouter(prefix="/insight-groups", tags=["insight-groups"])
router = APIRouter(prefix="/insights", tags=["insights"])


# ---- 気づき一覧（api.md 7-4） ----


@groups_router.get("", response_model=InsightGroupList)
def list_groups(
    user: CurrentUser,
    db: DbSession,
    sort: Annotated[GroupSort, Query()] = GroupSort.RECENT,
    cursor: Annotated[str | None, Query()] = None,
) -> InsightGroupList:
    items, next_cursor = insights_service.list_groups(db, user.id, sort, cursor)
    return InsightGroupList(items=items, next_cursor=next_cursor)


@groups_router.get("/{group_id}", response_model=InsightGroupDetail)
def get_group(group_id: uuid.UUID, user: CurrentUser, db: DbSession) -> InsightGroupDetail:
    return insights_service.get_group(db, user.id, group_id)


@groups_router.get("/{group_id}/insights", response_model=InsightCardList)
def list_group_insights(
    group_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    cursor: Annotated[str | None, Query()] = None,
) -> InsightCardList:
    items, next_cursor = insights_service.list_group_insights(db, user.id, group_id, cursor)
    return InsightCardList(items=items, next_cursor=next_cursor)


# ---- 気づき（api.md 7-5） ----


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CreatedInsight)
def create_insight(body: InsightCreate, user: CurrentUser, db: DbSession, response: Response) -> CreatedInsight:
    insight_id = insights_service.create_insight(
        db, user.id, book_id=body.book_id, page=body.page, quote=body.quote, body=body.body
    )
    response.headers["Location"] = f"/api/v1/insights/{insight_id}"
    return CreatedInsight(id=insight_id)


@router.get("/{insight_id}", response_model=InsightDetail)
def get_insight(insight_id: uuid.UUID, user: CurrentUser, db: DbSession) -> InsightDetail:
    return insights_service.get_insight(db, user.id, insight_id)


@router.patch("/{insight_id}", status_code=status.HTTP_204_NO_CONTENT)
def update_insight(insight_id: uuid.UUID, body: InsightUpdate, user: CurrentUser, db: DbSession) -> Response:
    # 送られた項目（null を含む）だけを取り出す
    insights_service.update_insight(db, user.id, insight_id, body.model_dump(exclude_unset=True))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{insight_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_insight(insight_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    insights_service.delete_insight(db, user.id, insight_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
