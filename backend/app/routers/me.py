from fastapi import APIRouter

from app.dependencies import CurrentUser, DbSession
from app.models import User
from app.schemas.ai_proposal import AiUsageResponse
from app.schemas.user import UserResponse
from app.services import ai_proposals

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=UserResponse)
def get_me(user: CurrentUser) -> User:
    return user


@router.get("/ai-usage", response_model=AiUsageResponse)
def get_ai_usage(user: CurrentUser, db: DbSession) -> dict:
    return ai_proposals.usage(db, user.id)
