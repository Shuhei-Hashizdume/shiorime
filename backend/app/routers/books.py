import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.dependencies import CurrentUser, DbSession
from app.models import ReadingStatus
from app.schemas.book import (
    BookDetail,
    BookList,
    BookListItem,
    BookStatusUpdate,
    BookUpdate,
    CatalogBookCreate,
    CreatedBook,
    ManualBookCreate,
)
from app.services import books as books_service
from app.services.google_books import GoogleBooksClient, get_google_books

router = APIRouter(prefix="/books", tags=["books"])

GoogleBooks = Annotated[GoogleBooksClient, Depends(get_google_books)]


def _created(response: Response, book_id: uuid.UUID) -> CreatedBook:
    response.headers["Location"] = f"/api/v1/books/{book_id}"
    return CreatedBook(id=book_id)


@router.get("", response_model=BookList)
def list_books(
    user: CurrentUser,
    db: DbSession,
    status_: Annotated[ReadingStatus | None, Query(alias="status")] = None,
    cursor: Annotated[str | None, Query()] = None,
) -> BookList:
    page = books_service.list_books(db, user.id, status_, cursor)
    return BookList(
        items=[BookListItem.model_validate(b) for b in page.items],
        total=page.total,
        next_cursor=page.next_cursor,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CreatedBook)
def create_manual_book(body: ManualBookCreate, user: CurrentUser, db: DbSession, response: Response) -> CreatedBook:
    book_id = books_service.create_manual_book(db, user.id, title=body.title, author=body.author, status=body.status)
    return _created(response, book_id)


# /books/{book_id} より先に定義する
@router.post("/from-catalog", status_code=status.HTTP_201_CREATED, response_model=CreatedBook)
def create_catalog_book(
    body: CatalogBookCreate, user: CurrentUser, db: DbSession, google_books: GoogleBooks, response: Response
) -> CreatedBook:
    book_id = books_service.create_catalog_book(
        db, user.id, google_books, google_volume_id=body.google_volume_id, status=body.status
    )
    return _created(response, book_id)


@router.get("/{book_id}", response_model=BookDetail)
def get_book(book_id: uuid.UUID, user: CurrentUser, db: DbSession) -> BookDetail:
    return books_service.get_book(db, user.id, book_id)


@router.patch("/{book_id}", response_model=BookDetail)
def update_book(book_id: uuid.UUID, body: BookUpdate, user: CurrentUser, db: DbSession) -> BookDetail:
    changes = {field: getattr(body, field) for field in body.model_fields_set}
    return books_service.update_book(db, user.id, book_id, changes)


@router.put("/{book_id}/status", response_model=BookDetail)
def update_status(book_id: uuid.UUID, body: BookStatusUpdate, user: CurrentUser, db: DbSession) -> BookDetail:
    return books_service.update_status(db, user.id, book_id, body.status)


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(book_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    books_service.delete_book(db, user.id, book_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
