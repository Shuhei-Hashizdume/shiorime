from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import AfterValidator

from app.core.text import text_validator
from app.dependencies import CurrentUser, DbSession
from app.schemas.book import CatalogSearchResult
from app.services import books as books_service
from app.services.google_books import GoogleBooksClient, get_google_books

router = APIRouter(prefix="/catalog", tags=["catalog"])

# 前後の空白を除いて空なら 422（required）
SEARCH_WORDS_MAX_CHARS = 200
SearchWords = Annotated[str, AfterValidator(text_validator(SEARCH_WORDS_MAX_CHARS)), Query()]


@router.get("/search", response_model=CatalogSearchResult)
def search(
    q: SearchWords,
    user: CurrentUser,
    db: DbSession,
    google_books: Annotated[GoogleBooksClient, Depends(get_google_books)],
    offset: Annotated[int, Query(ge=0, le=1000)] = 0,
) -> CatalogSearchResult:
    items, next_offset = books_service.search_catalog(db, user.id, google_books, q=q, offset=offset)
    return CatalogSearchResult(items=items, next_offset=next_offset)
