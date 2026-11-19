"""Google Books API とのやりとり（api.md 4章・7-3）。

テストでは偽物に置き換えるため、routers は get_google_books() を Depends で受け取る。
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.config import settings
from app.core.errors import AppError
from app.core.text import count_chars, normalize, truncate
from app.models.book import BOOK_AUTHOR_MAX_CHARS, BOOK_TITLE_MAX_CHARS

logger = logging.getLogger(__name__)

BASE_URL = "https://www.googleapis.com/books/v1/volumes"
# 1回の待ち時間の上限。画面の利用者を長く待たせないため
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
# 使う項目だけを頼む（使わない項目は取らない・保存しない。api.md 4-4）
FIELDS_VOLUME = "id,volumeInfo(title,authors,publishedDate,imageLinks/thumbnail,infoLink,industryIdentifiers)"
FIELDS_SEARCH = f"items({FIELDS_VOLUME})"


@dataclass(frozen=True)
class CatalogBook:
    """Google Books の本1冊を、SHIORIME で使う形に整えたもの。"""

    google_volume_id: str
    title: str
    authors: str | None
    published_year: int | None
    cover_url: str | None
    info_link: str | None
    isbn: str | None


class GoogleBooksClient(Protocol):
    def search(self, q: str, offset: int, limit: int) -> list[CatalogBook]: ...

    def get_volume(self, google_volume_id: str) -> CatalogBook | None: ...


# ---- 整え方（4-1・4-4） ----


def format_title(title: str | None) -> str:
    value = normalize(title or "")
    if value == "":
        return "（タイトルなし）"
    return truncate(value, BOOK_TITLE_MAX_CHARS)


def format_authors(authors: list[str] | None) -> str | None:
    """著者を「、」でつなぐ。100文字に入りきらない分は「ほか」にする（api.md 4-1）。"""
    names = [normalize(a) for a in authors or [] if normalize(a)]
    if not names:
        return None
    joined = "、".join(names)
    if count_chars(joined) <= BOOK_AUTHOR_MAX_CHARS:
        return joined
    if count_chars(names[0] + " ほか") > BOOK_AUTHOR_MAX_CHARS:
        return truncate(names[0], BOOK_AUTHOR_MAX_CHARS)
    kept = [names[0]]
    for name in names[1:]:
        candidate = "、".join([*kept, name]) + " ほか"
        if count_chars(candidate) > BOOK_AUTHOR_MAX_CHARS:
            break
        kept.append(name)
    return "、".join(kept) + " ほか"


def to_https(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("http://"):
        return "https://" + url[len("http://") :]
    if url.startswith("https://"):
        return url
    return None


def published_year(published_date: str | None) -> int | None:
    match = re.match(r"^(\d{4})", published_date or "")
    return int(match.group(1)) if match else None


def isbn13(identifiers: list[dict[str, Any]] | None) -> str | None:
    """13桁の ISBN があるときだけ、ハイフンを除いて返す（api.md 7-3）。"""
    for identifier in identifiers or []:
        if identifier.get("type") == "ISBN_13":
            digits = re.sub(r"[^0-9]", "", identifier.get("identifier", ""))
            if len(digits) == 13:
                return digits
    return None


def to_catalog_book(volume: dict[str, Any]) -> CatalogBook:
    info = volume.get("volumeInfo") or {}
    return CatalogBook(
        google_volume_id=volume["id"],
        title=format_title(info.get("title")),
        authors=format_authors(info.get("authors")),
        published_year=published_year(info.get("publishedDate")),
        cover_url=to_https((info.get("imageLinks") or {}).get("thumbnail")),
        info_link=to_https(info.get("infoLink")),
        isbn=isbn13(info.get("industryIdentifiers")),
    )


# ---- エラー（4-5） ----

_QUOTA_REASONS = {"rateLimitExceeded", "dailyLimitExceeded", "quotaExceeded", "userRateLimitExceeded"}


def _is_quota_error(response: httpx.Response) -> bool:
    if response.status_code == 429:
        return True
    if response.status_code != 403:
        return False
    try:
        errors = response.json().get("error", {}).get("errors", [])
    except ValueError:
        return False
    return any(e.get("reason") in _QUOTA_REASONS for e in errors)


def limit_error() -> AppError:
    return AppError(503, "BOOK_SEARCH_LIMIT", "Google Books の利用枠を超えました")


def failed_error() -> AppError:
    return AppError(502, "BOOK_SEARCH_FAILED", "Google Books から返事がありません")


# ---- 本物 ----


class HttpGoogleBooksClient:
    def __init__(self) -> None:
        self._client = httpx.Client(timeout=TIMEOUT)

    def _get(self, url: str, params: dict[str, Any]) -> httpx.Response:
        # キーは URL ではなくヘッダーで送る（URL ごとログに残らないようにするため。api.md 4-2）
        headers = {"X-goog-api-key": settings.google_books_api_key.get_secret_value()}
        try:
            response = self._client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("google books request failed: %s", type(exc).__name__)
            raise failed_error() from None
        if _is_quota_error(response):
            # ふつうは起きないので、作る側が気づけるよう ERROR で残す（api.md 4-5）
            logger.error("google books quota exceeded: status=%s", response.status_code)
            raise limit_error()
        if response.status_code in (400, 401, 403):
            # API キーの誤り・制限など。利用者ではなく作る側が直すものなので ERROR で残す
            logger.error("google books rejected the request: status=%s", response.status_code)
            raise failed_error()
        return response

    def search(self, q: str, offset: int, limit: int) -> list[CatalogBook]:
        response = self._get(
            BASE_URL,
            {"q": q, "startIndex": offset, "maxResults": limit, "printType": "books", "fields": FIELDS_SEARCH},
        )
        if response.status_code != 200:
            logger.warning("google books search failed: status=%s", response.status_code)
            raise failed_error()
        return [to_catalog_book(v) for v in response.json().get("items", []) if v.get("id")]

    def get_volume(self, google_volume_id: str) -> CatalogBook | None:
        response = self._get(f"{BASE_URL}/{google_volume_id}", {"fields": FIELDS_VOLUME})
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            logger.warning("google books volume failed: status=%s", response.status_code)
            raise failed_error()
        return to_catalog_book(response.json())


_client: HttpGoogleBooksClient | None = None


def get_google_books() -> GoogleBooksClient:
    global _client
    if _client is None:
        _client = HttpGoogleBooksClient()
    return _client
