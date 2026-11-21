import uuid
from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator, BaseModel, ConfigDict, StrictBool
from pydantic_core import PydanticCustomError

from app.core.text import count_chars, length_range_validator, normalize, required_text
from app.models import UserAttribute
from app.models.user import EMAIL_MAX_CHARS

PASSWORD_MIN_CHARS = 8
PASSWORD_MAX_CHARS = 128


def _normalize_email(value: str) -> str:
    """前後の空白を除いて小文字にそろえる（database.md 3-1）。"""
    return normalize(value).lower()


def _validate_new_email(value: str) -> str:
    value = _normalize_email(value)
    if value == "":
        raise PydanticCustomError("required", "入力してください")
    if len(value) > EMAIL_MAX_CHARS * 4 or count_chars(value) > EMAIL_MAX_CHARS:
        raise PydanticCustomError("too_long", "{limit}文字以内で入力してください", {"limit": EMAIL_MAX_CHARS})
    try:
        validate_email(value, check_deliverability=False)
    except EmailNotValidError:
        raise PydanticCustomError("invalid_format", "メールアドレスの形式で入力してください") from None
    return value


def _validate_login_email(value: str) -> str:
    # ログインでは形を確かめない（違えば「メールアドレスかパスワードが違います」になるだけ）
    value = _normalize_email(value)
    if value == "":
        raise PydanticCustomError("required", "入力してください")
    return value


def _must_agree(value: bool) -> bool:
    if value is not True:
        raise PydanticCustomError("required", "同意が必要です")
    return value


NewEmail = Annotated[str, AfterValidator(_validate_new_email)]
LoginEmail = Annotated[str, AfterValidator(_validate_login_email)]
NewPassword = Annotated[str, AfterValidator(length_range_validator(PASSWORD_MIN_CHARS, PASSWORD_MAX_CHARS))]
CurrentPassword = Annotated[str, AfterValidator(required_text)]
AgreedToTerms = Annotated[StrictBool, AfterValidator(_must_agree)]


class RegisterRequest(BaseModel):
    email: NewEmail
    password: NewPassword
    attribute: UserAttribute
    agreed_to_terms: AgreedToTerms


class LoginRequest(BaseModel):
    email: LoginEmail
    password: CurrentPassword


class UserResponse(BaseModel):
    """新規登録・ログイン・GET /me で同じ形を返す（api.md 7-1・7-2）。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    attribute: UserAttribute


# ---- プロフィール（api.md 7-2） ----


class AttributeUpdate(BaseModel):
    """変えられるのは属性だけ。メールアドレスなどほかの項目は 422。"""

    model_config = ConfigDict(extra="forbid")

    attribute: UserAttribute


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: CurrentPassword
    new_password: NewPassword


class WithdrawRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: CurrentPassword
