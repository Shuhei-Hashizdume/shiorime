"""本の検索（Google Books）と、整え方（api.md 4章・7-3）。"""

from fastapi.testclient import TestClient

from app.services.google_books import (
    failed_error,
    format_authors,
    format_title,
    isbn13,
    limit_error,
    published_year,
    to_https,
)
from tests.fakes import FakeGoogleBooks, catalog_book

SEARCH = "/api/v1/catalog/search"


def test_search_marks_books_on_my_shelf(user_client: TestClient, google_books: FakeGoogleBooks) -> None:
    google_books.add(catalog_book("vol1"), catalog_book("vol2", "別の本"))
    on_shelf = user_client.post(
        "/api/v1/books/from-catalog", json={"google_volume_id": "vol1", "status": "reading"}
    ).json()["id"]

    response = user_client.get(SEARCH, params={"q": " 勇気 "})

    assert response.status_code == 200
    body = response.json()
    assert body["next_offset"] is None
    assert [(i["google_volume_id"], i["shelf_book_id"]) for i in body["items"]] == [
        ("vol1", on_shelf),
        ("vol2", None),
    ]
    assert set(body["items"][0]) == {
        "google_volume_id",
        "title",
        "authors",
        "published_year",
        "cover_url",
        "info_link",
        "shelf_book_id",
    }
    # 前後の空白を除いて頼み、続きがあるかを知るために21件頼む
    assert google_books.search_calls == [("勇気", 0, 21)]


def test_search_does_not_mark_other_users_books(
    user_client: TestClient, other_client: TestClient, google_books: FakeGoogleBooks
) -> None:
    google_books.add(catalog_book("vol1"))
    other_client.post("/api/v1/books/from-catalog", json={"google_volume_id": "vol1", "status": "reading"})

    item = user_client.get(SEARCH, params={"q": "勇気"}).json()["items"][0]

    assert item["shelf_book_id"] is None


def test_search_next_offset(user_client: TestClient, google_books: FakeGoogleBooks) -> None:
    google_books.add(*[catalog_book(f"v{i}") for i in range(25)])

    first = user_client.get(SEARCH, params={"q": "本"}).json()
    assert len(first["items"]) == 20
    assert first["next_offset"] == 20

    second = user_client.get(SEARCH, params={"q": "本", "offset": 20}).json()
    assert len(second["items"]) == 5
    assert second["next_offset"] is None


def test_search_validation(user_client: TestClient, google_books: FakeGoogleBooks) -> None:
    empty = user_client.get(SEARCH, params={"q": "  "})
    assert empty.status_code == 422
    assert empty.json()["error"]["fields"] == [{"field": "q", "reason": "required"}]

    missing = user_client.get(SEARCH)
    assert missing.json()["error"]["fields"] == [{"field": "q", "reason": "required"}]

    assert user_client.get(SEARCH, params={"q": "本", "offset": -1}).status_code == 422
    assert google_books.search_calls == []


def test_search_rate_limit_per_user(
    user_client: TestClient, other_client: TestClient, google_books: FakeGoogleBooks
) -> None:
    for _ in range(10):
        assert user_client.get(SEARCH, params={"q": "本"}).status_code == 200

    response = user_client.get(SEARCH, params={"q": "本"})

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "SEARCH_RATE_LIMIT"
    assert "retry-after" in response.headers
    # 別の人は数えない
    assert other_client.get(SEARCH, params={"q": "本"}).status_code == 200


def test_search_errors(user_client: TestClient, google_books: FakeGoogleBooks) -> None:
    google_books.error = limit_error()
    limit = user_client.get(SEARCH, params={"q": "本"})
    assert (limit.status_code, limit.json()["error"]["code"]) == (503, "BOOK_SEARCH_LIMIT")

    google_books.error = failed_error()
    failed = user_client.get(SEARCH, params={"q": "本"})
    assert (failed.status_code, failed.json()["error"]["code"]) == (502, "BOOK_SEARCH_FAILED")


def test_search_requires_login(client: TestClient, google_books: FakeGoogleBooks) -> None:
    assert client.get(SEARCH, params={"q": "本"}).status_code == 401


# ---- 整え方 ----


def test_long_title_is_truncated_to_200() -> None:
    title = format_title("あ" * 250)
    assert title == "あ" * 199 + "…"


def test_title_is_not_cut_inside_emoji() -> None:
    title = format_title("👨‍👩‍👧" * 201)
    assert title == "👨‍👩‍👧" * 199 + "…"


def test_authors_are_joined() -> None:
    assert format_authors(["岸見一郎", "古賀史健"]) == "岸見一郎、古賀史健"
    assert format_authors([]) is None
    assert format_authors(None) is None


def test_too_many_authors_become_hoka() -> None:
    names = ["著" * 30, "者" * 30, "名" * 30, "前" * 30]
    result = format_authors(names)
    assert result == "著" * 30 + "、" + "者" * 30 + "、" + "名" * 30 + " ほか"
    assert len(result) <= 100


def test_first_author_too_long() -> None:
    assert format_authors(["あ" * 120, "い"]) == "あ" * 99 + "…"


def test_cover_url_becomes_https() -> None:
    assert to_https("http://books.google.com/x.jpg") == "https://books.google.com/x.jpg"
    assert to_https("https://books.google.com/x.jpg") == "https://books.google.com/x.jpg"
    assert to_https("javascript:alert(1)") is None
    assert to_https(None) is None


def test_isbn_13_only() -> None:
    assert isbn13([{"type": "ISBN_13", "identifier": "978-4-478-02581-9"}]) == "9784478025819"
    assert isbn13([{"type": "ISBN_10", "identifier": "4478025819"}]) is None
    assert isbn13(None) is None


def test_published_year() -> None:
    assert published_year("2013-12-13") == 2013
    assert published_year("2013") == 2013
    assert published_year(None) is None


# ---- 本物の部品の、Google Books の返事の扱い ----

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.core.errors import AppError  # noqa: E402
from app.services.google_books import HttpGoogleBooksClient  # noqa: E402


def _client_returning(status: int, body: dict) -> HttpGoogleBooksClient:
    client = HttpGoogleBooksClient()
    client._client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body)))
    return client


def test_real_client_sends_key_in_header_not_url() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"items": []})

    client = HttpGoogleBooksClient()
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    client.search("本", 0, 21)

    assert "x-goog-api-key" in seen[0].headers
    assert "key=" not in str(seen[0].url)


def test_real_client_maps_volume() -> None:
    client = _client_returning(
        200,
        {
            "id": "vol1",
            "volumeInfo": {
                "title": "嫌われる勇気",
                "authors": ["岸見一郎", "古賀史健"],
                "publishedDate": "2013-12-13",
                "imageLinks": {"thumbnail": "http://books.google.com/x.jpg"},
                "infoLink": "http://books.google.com/books?id=vol1",
                "industryIdentifiers": [{"type": "ISBN_13", "identifier": "9784478025819"}],
            },
        },
    )

    book = client.get_volume("vol1")

    assert book is not None
    assert book.cover_url == "https://books.google.com/x.jpg"
    assert book.isbn == "9784478025819"
    assert book.published_year == 2013


@pytest.mark.parametrize(
    ("status", "body", "code"),
    [
        (429, {}, "BOOK_SEARCH_LIMIT"),
        (403, {"error": {"errors": [{"reason": "dailyLimitExceeded"}]}}, "BOOK_SEARCH_LIMIT"),
        (400, {"error": {"errors": [{"reason": "keyInvalid"}]}}, "BOOK_SEARCH_FAILED"),
        (500, {}, "BOOK_SEARCH_FAILED"),
    ],
)
def test_real_client_errors(status: int, body: dict, code: str) -> None:
    with pytest.raises(AppError) as exc_info:
        _client_returning(status, body).search("本", 0, 21)
    assert exc_info.value.code == code


def test_real_client_volume_not_found() -> None:
    assert _client_returning(404, {}).get_volume("nothing") is None


def test_real_client_timeout_is_failed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = HttpGoogleBooksClient()
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(AppError) as exc_info:
        client.get_volume("vol1")
    assert exc_info.value.code == "BOOK_SEARCH_FAILED"
