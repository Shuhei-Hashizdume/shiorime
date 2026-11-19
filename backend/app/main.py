from fastapi import FastAPI

from app.core.errors import register_error_handlers
from app.routers import auth, books, catalog, health, me

app = FastAPI(title="SHIORIME API")

register_error_handlers(app)

app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(me.router, prefix="/api/v1")
app.include_router(books.router, prefix="/api/v1")
app.include_router(catalog.router, prefix="/api/v1")
