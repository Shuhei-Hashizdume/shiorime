from app.core.errors import AppError
from app.services.google_books import CatalogBook


def catalog_book(volume_id: str, title: str = "嫌われる勇気", **overrides) -> CatalogBook:
    values = {
        "google_volume_id": volume_id,
        "title": title,
        "authors": "岸見一郎、古賀史健",
        "published_year": 2013,
        "cover_url": f"https://books.google.com/{volume_id}.jpg",
        "info_link": f"https://books.google.com/books?id={volume_id}",
        "isbn": "9784478025819",
    }
    values.update(overrides)
    return CatalogBook(**values)


class FakeGoogleBooks:
    """Google Books の偽物。books に入れた本を返し、呼ばれた回数を数える。"""

    def __init__(self) -> None:
        self.books: dict[str, CatalogBook] = {}
        self.search_calls: list[tuple[str, int, int]] = []
        self.get_calls: list[str] = []
        self.error: AppError | None = None

    def add(self, *books: CatalogBook) -> None:
        for book in books:
            self.books[book.google_volume_id] = book

    def search(self, q: str, offset: int, limit: int) -> list[CatalogBook]:
        self.search_calls.append((q, offset, limit))
        if self.error:
            raise self.error
        return list(self.books.values())[offset : offset + limit]

    def get_volume(self, google_volume_id: str) -> CatalogBook | None:
        self.get_calls.append(google_volume_id)
        if self.error:
            raise self.error
        return self.books.get(google_volume_id)
