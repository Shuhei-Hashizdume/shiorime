from fastapi import APIRouter, Response, status

from app.core.security import clear_auth_cookie
from app.dependencies import CurrentUser, DbSession
from app.models import User
from app.schemas.ai_proposal import AiUsageResponse
from app.schemas.user import AttributeUpdate, PasswordChangeRequest, UserResponse, WithdrawRequest
from app.services import ai_proposals
from app.services import me as me_service

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=UserResponse)
def get_me(user: CurrentUser) -> User:
    return user


@router.patch("", response_model=UserResponse)
def update_me(body: AttributeUpdate, user: CurrentUser, db: DbSession) -> User:
    return me_service.change_attribute(db, user, body.attribute)


@router.get("/ai-usage", response_model=AiUsageResponse)
def get_ai_usage(user: CurrentUser, db: DbSession) -> dict:
    return ai_proposals.usage(db, user.id)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: PasswordChangeRequest, user: CurrentUser, db: DbSession) -> Response:
    me_service.change_password(db, user, body.current_password, body.new_password)
    # この端末の Cookie も消す（ほかの端末は、バージョン番号が合わなくなって断られる）
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookie(response)
    return response


@router.post("/withdraw", status_code=status.HTTP_204_NO_CONTENT)
def withdraw(body: WithdrawRequest, user: CurrentUser, db: DbSession) -> Response:
    me_service.withdraw(db, user, body.password)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookie(response)
    return response
