"""一覧の続きの位置（カーソル。api.md 1-5）。

中身は「最後に渡した1件の並びの値」を JSON にして base64url で包んだもの。画面は中身を気にせずそのまま送り返す。
"""

import base64
import binascii
import json
from typing import Any

from app.core.errors import AppError


def encode_cursor(data: dict[str, Any]) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def invalid_cursor() -> AppError:
    return AppError(
        422,
        "VALIDATION_ERROR",
        "cursor が正しくありません",
        fields=[{"field": "cursor", "reason": "invalid_format"}],
    )


def decode_cursor(cursor: str) -> dict[str, Any]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        data = json.loads(raw)
    except (binascii.Error, ValueError):
        raise invalid_cursor() from None
    if not isinstance(data, dict):
        raise invalid_cursor()
    return data
