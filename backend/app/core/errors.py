"""エラーの形を api.md 1-3 の {"error": {"code", "message", "fields", "details"}} にそろえる。"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.security import clear_auth_cookie

logger = logging.getLogger(__name__)


class AppError(Exception):
    """アプリの決まりごとで断るときに投げる例外。

    services はステータスコードとエラーコードをこの例外に入れて投げ、
    下の例外ハンドラーが api.md 1-3 の形の返事に直す。
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        fields: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
        clear_auth_cookie: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.fields = fields
        self.headers = headers
        # TOKEN_EXPIRED などで、ログインの Cookie を同時に消すとき（api.md 3-3）
        self.clear_auth_cookie = clear_auth_cookie


def error_body(
    code: str,
    message: str,
    *,
    fields: list[dict[str, Any]] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if fields is not None:
        error["fields"] = fields
    if details is not None:
        error["details"] = details
    return {"error": error}


# api.md 1-3 の reason の一覧。自分で作る確かめ（core/text.py など）は、この名前で誤りを出す。
REASONS = {"required", "too_long", "out_of_range", "invalid_format", "invalid_value", "not_allowed"}

# Pydantic が自動で出す誤りの種類 → reason
PYDANTIC_TYPE_TO_REASON = {
    "missing": "required",
    "extra_forbidden": "not_allowed",
    "enum": "invalid_value",
    "literal_error": "invalid_value",
    "json_invalid": "invalid_format",
    "uuid_parsing": "invalid_format",
    "uuid_type": "invalid_format",
    "string_pattern_mismatch": "invalid_format",
    "int_parsing": "invalid_format",
    "greater_than_equal": "out_of_range",
    "less_than_equal": "out_of_range",
}


def to_field_error(error: dict[str, Any]) -> dict[str, Any]:
    """Pydantic の誤り1つを、api.md 1-3 の error.fields の1件に直す。"""
    loc = error.get("loc", ())
    # loc の先頭は "body"・"query" などの場所なので、項目名だけにする
    field = ".".join(str(part) for part in loc[1:]) or (str(loc[0]) if loc else "")

    error_type = error.get("type", "")
    if error_type in REASONS:
        reason = error_type
    else:
        reason = PYDANTIC_TYPE_TO_REASON.get(error_type, "invalid_value")

    item: dict[str, Any] = {"field": field, "reason": reason}
    ctx = error.get("ctx") or {}
    for key in ("limit", "min", "max"):
        if key in ctx:
            item[key] = ctx[key]
    return item


async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    response = JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message, fields=exc.fields, details=exc.details),
        headers=exc.headers,
    )
    if exc.clear_auth_cookie:
        clear_auth_cookie(response)
    return response


async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = [to_field_error(error) for error in exc.errors()]
    return JSONResponse(
        status_code=422,
        content=error_body("VALIDATION_ERROR", "入力が正しくありません", fields=fields),
    )


HTTP_STATUS_TO_CODE = {
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
}


async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = HTTP_STATUS_TO_CODE.get(exc.status_code, "HTTP_ERROR")
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, str(exc.detail)),
        headers=getattr(exc, "headers", None),
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # 中身（入力した文など）はログに出さず、例外の種類とスタックトレースだけを残す（notes.md 5章）
    logger.exception("unexpected error: %s", type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content=error_body("INTERNAL_ERROR", "サーバーでエラーが起きました"),
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, handle_validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, handle_unexpected_error)
