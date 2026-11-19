from fastapi import APIRouter

from app.dependencies import CurrentUser
from app.models import User
from app.schemas.user import UserResponse

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=UserResponse)
def get_me(user: CurrentUser) -> User:
    return user
