import uuid
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

from app.core.text import optional_text_validator, text_validator
from app.models.book import BOOK_AUTHOR_MAX_CHARS, BOOK_TITLE_MAX_CHARS, ReadingStatus

BookTitle = Annotated[str, AfterValidator(text_validator(BOOK_TITLE_MAX_CHARS))]
BookAuthor = Annotated[str | None, AfterValidator(optional_text_validator(BOOK_AUTHOR_MAX_CHARS))]
# Google Books の識別子。URL のパスに入れるので、使える文字を決めておく
GoogleVolumeId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


class StrictModel(BaseModel):
    """決めた項目以外を送られたら 422（not_allowed）にする。"""

    model_config = ConfigDict(extra="forbid")


# ---- 受け取るもの ----


class ManualBookCreate(StrictModel):
    title: BookTitle
    author: BookAuthor = None
    status: ReadingStatus


class CatalogBookCreate(StrictModel):
    google_volume_id: GoogleVolumeId
    status: ReadingStatus


class BookUpdate(StrictModel):
    title: BookTitle | None = None
    author: BookAuthor = None

    @model_validator(mode="after")
    def check_fields(self) -> "BookUpdate":
        if not self.model_fields_set:
            raise PydanticCustomError("required", "タイトルか著者を送ってください")
        if "title" in self.model_fields_set and self.title is None:
            # タイトルは空にできない
            raise PydanticCustomError("required", "タイトルを入力してください")
        return self


class BookStatusUpdate(StrictModel):
    status: ReadingStatus


# ---- 返すもの ----


class BookListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    cover_url: str | None
    status: ReadingStatus


class BookList(BaseModel):
    items: list[BookListItem]
    total: int
    next_cursor: str | None


class BookDetail(BaseModel):
    id: uuid.UUID
    title: str
    author: str | None
    cover_url: str | None
    status: ReadingStatus
    google_volume_id: str | None
    insight_count: int


class CreatedBook(BaseModel):
    id: uuid.UUID


class CatalogItem(BaseModel):
    google_volume_id: str
    title: str
    authors: str | None
    published_year: int | None
    cover_url: str | None
    info_link: str | None
    shelf_book_id: uuid.UUID | None


class CatalogSearchResult(BaseModel):
    items: list[CatalogItem]
    next_offset: int | None = Field(description="続きがなければ null")
