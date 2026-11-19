from fastapi import APIRouter, Request, Response, status

from app.core import clock
from app.core.request import get_client_ip
from app.core.security import clear_auth_cookie, create_access_token, set_auth_cookie
from app.dependencies import DbSession
from app.models import User
from app.schemas.user import LoginRequest, RegisterRequest, UserResponse
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _log_in(response: Response, user: User) -> None:
    token = create_access_token(user.id, user.token_version, clock.now())
    set_auth_cookie(response, token)


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
def register(body: RegisterRequest, request: Request, response: Response, db: DbSession) -> User:
    user = auth_service.register(
        db,
        email=body.email,
        password=body.password,
        attribute=body.attribute,
        client_ip=get_client_ip(request),
    )
    # 登録できたら、そのままログイン状態にする（api.md 7-1）
    _log_in(response, user)
    return user


@router.post("/login", response_model=UserResponse)
def login(body: LoginRequest, request: Request, response: Response, db: DbSession) -> User:
    user = auth_service.login(
        db,
        email=body.email,
        password=body.password,
        client_ip=get_client_ip(request),
    )
    _log_in(response, user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout() -> Response:
    # ログインしていなくても、いつでも 204（冪等。api.md 7-1）
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookie(response)
    return response
