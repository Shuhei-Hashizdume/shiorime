import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Response, status

from app.dependencies import CurrentUser, DbSession
from app.schemas.ai_proposal import AnswerRequest, ProposalResponse, StartedProposal
from app.services import ai_proposals as service
from app.services.ai_client import AiClient, get_ai_client

router = APIRouter(tags=["ai-proposals"])

Ai = Annotated[AiClient, Depends(get_ai_client)]


@router.post(
    "/insights/{insight_id}/ai-proposals",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=StartedProposal,
)
def start(
    insight_id: uuid.UUID,
    idempotency_key: Annotated[uuid.UUID, Header(alias="Idempotency-Key")],
    user: CurrentUser,
    db: DbSession,
    ai: Ai,
    background: BackgroundTasks,
    response: Response,
) -> StartedProposal:
    proposal_id, created = service.start(db, user.id, insight_id, idempotency_key)
    if created:
        # 受け付けたらすぐ返し、深掘りは裏で作る（api.md 2章）
        background.add_task(service.run_question, proposal_id, ai)
    response.headers["Location"] = f"/api/v1/ai-proposals/{proposal_id}"
    return StartedProposal(id=proposal_id)


@router.get("/ai-proposals/{proposal_id}", response_model=ProposalResponse)
def get(proposal_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict:
    return service.get(db, user.id, proposal_id)


@router.post("/ai-proposals/{proposal_id}/answer", status_code=status.HTTP_202_ACCEPTED)
def answer(
    proposal_id: uuid.UUID, body: AnswerRequest, user: CurrentUser, db: DbSession, ai: Ai, background: BackgroundTasks
) -> Response:
    service.answer(db, user.id, proposal_id, body.answer)
    background.add_task(service.run_plans, proposal_id, ai)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/ai-proposals/{proposal_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry(
    proposal_id: uuid.UUID, body: AnswerRequest, user: CurrentUser, db: DbSession, ai: Ai, background: BackgroundTasks
) -> Response:
    service.retry(db, user.id, proposal_id, body.answer)
    background.add_task(service.run_plans, proposal_id, ai)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/ai-proposals/{proposal_id}/abandon", status_code=status.HTTP_204_NO_CONTENT)
def abandon(proposal_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    service.abandon(db, user.id, proposal_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
