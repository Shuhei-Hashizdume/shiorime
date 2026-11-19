import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, StrictInt, model_validator
from pydantic_core import PydanticCustomError

from app.core.text import optional_text_validator, text_validator
from app.models.insight import INSIGHT_BODY_MAX_CHARS, INSIGHT_PAGE_MAX, INSIGHT_PAGE_MIN, INSIGHT_QUOTE_MAX_CHARS


def _check_page(value: int | None) -> int | None:
    if value is not None and not INSIGHT_PAGE_MIN <= value <= INSIGHT_PAGE_MAX:
        raise PydanticCustomError(
            "out_of_range",
            "{min}〜{max}で入力してください",
            {"min": INSIGHT_PAGE_MIN, "max": INSIGHT_PAGE_MAX},
        )
    return value


InsightBody = Annotated[str, AfterValidator(text_validator(INSIGHT_BODY_MAX_CHARS))]
InsightQuote = Annotated[str | None, AfterValidator(optional_text_validator(INSIGHT_QUOTE_MAX_CHARS))]
InsightPage = Annotated[StrictInt | None, AfterValidator(_check_page)]


class GroupSort(StrEnum):
    """気づき一覧の並び順（api.md 7-4）"""

    RECENT = "recent"
    MANY = "many"
    FEW = "few"


# ---- 受け取るもの ----


class InsightCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    book_id: uuid.UUID
    page: InsightPage = None
    quote: InsightQuote = None
    body: InsightBody


class InsightUpdate(BaseModel):
    """送らない＝変えない、null＝消す（部分更新。api.md 7-5）"""

    model_config = ConfigDict(extra="forbid")

    page: InsightPage = None
    quote: InsightQuote = None
    body: InsightBody | None = None

    @model_validator(mode="after")
    def body_cannot_be_removed(self) -> "InsightUpdate":
        if "body" in self.model_fields_set and self.body is None:
            raise PydanticCustomError("required", "本文は消せません")
        return self


# ---- 返すもの ----


class InsightGroup(BaseModel):
    id: uuid.UUID
    title: str
    cover_url: str | None
    insight_count: int
    last_written_at: datetime | None
    deleted: bool


class InsightGroupDetail(InsightGroup):
    author: str | None


class InsightGroupList(BaseModel):
    items: list[InsightGroup]
    next_cursor: str | None


class InsightCard(BaseModel):
    id: uuid.UUID
    page: int | None
    quote: str | None
    body: str
    next_step_count: int
    created_at: datetime


class InsightCardList(BaseModel):
    items: list[InsightCard]
    next_cursor: str | None


class CreatedInsight(BaseModel):
    id: uuid.UUID


class InsightBook(BaseModel):
    id: uuid.UUID
    title: str
    author: str | None
    cover_url: str | None


class Plan(BaseModel):
    text: str


class LatestProposal(BaseModel):
    id: uuid.UUID
    completed_at: datetime
    plans: list[Plan]


class PendingProposal(BaseModel):
    id: uuid.UUID
    status: Literal["processing", "failed"]


class InsightDetail(BaseModel):
    id: uuid.UUID
    page: int | None
    quote: str | None
    body: str
    created_at: datetime
    book: InsightBook
    latest_proposal: LatestProposal | None
    pending_proposal: PendingProposal | None
