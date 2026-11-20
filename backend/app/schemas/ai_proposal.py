import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict

from app.core.text import text_validator
from app.models.ai_proposal import ANSWER_MAX_CHARS

Answer = Annotated[str, AfterValidator(text_validator(ANSWER_MAX_CHARS))]

ProposalApiStatus = Literal[
    "generating_question",
    "awaiting_answer",
    "generating_plans",
    "plan_failed",
    "completed",
    "question_failed",
    "retry_limit_reached",
]


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: Answer


class StartedProposal(BaseModel):
    id: uuid.UUID


class ProposalInsight(BaseModel):
    book_title: str
    page: int | None
    quote: str | None
    body: str


class Plan(BaseModel):
    text: str


class ProposalResponse(BaseModel):
    id: uuid.UUID
    status: ProposalApiStatus
    insight_id: uuid.UUID
    insight: ProposalInsight
    question: str | None
    answer: str | None
    plans: list[Plan] | None
    completed_at: datetime | None
    retries_left: int


class AiUsageResponse(BaseModel):
    remaining_today: int
    daily_limit: int
    app_limit_reached: bool
