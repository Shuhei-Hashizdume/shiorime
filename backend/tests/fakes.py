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


# ---- OpenAI の偽物（AI提案のテストで使う） ----

import threading  # noqa: E402
from collections.abc import Callable  # noqa: E402

from app.services.ai_client import AiError, InsightContext  # noqa: E402

QUESTION = "黙ってしまう直前、頭の中ではどんな言葉が浮かんでいますか？"
PLANS = ["次の会議で、結論から一言だけ発言する", "発言したあとの気持ちを1行メモする"]


class FakeAi:
    """AI の偽物。questions・plans に順番に返すもの（文字・リスト・AiError）を入れておく。空なら決まった答えを返す。

    - question_calls・plan_calls：呼ばれたときに受け取ったもの（何回呼ばれたかの確認に使う）
    - gate：入れておくと、質問を返す前に止まる（「処理中」を作るため）
    - before_question_returns：質問を返す直前に動かす処理（途中でやめられた場合を作るため）
    """

    def __init__(self) -> None:
        self.questions: list[str | AiError] = []
        self.plans: list[list[str] | AiError] = []
        self.question_calls: list[InsightContext] = []
        self.plan_calls: list[tuple[InsightContext, str, str]] = []
        self.gate: threading.Event | None = None
        self.before_question_returns: Callable[[], None] | None = None

    def generate_question(self, context: InsightContext) -> str:
        self.question_calls.append(context)
        if self.gate is not None:
            self.gate.wait(timeout=10)
        result = self.questions.pop(0) if self.questions else QUESTION
        if self.before_question_returns is not None:
            self.before_question_returns()
        if isinstance(result, AiError):
            raise result
        return result

    def generate_plans(self, context: InsightContext, question: str, answer: str) -> list[str]:
        self.plan_calls.append((context, question, answer))
        result = self.plans.pop(0) if self.plans else PLANS
        if isinstance(result, AiError):
            raise result
        return result
