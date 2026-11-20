from fastapi import FastAPI

from app.core.errors import register_error_handlers
from app.routers import ai_proposals, auth, books, catalog, health, insights, me

app = FastAPI(title="SHIORIME API")

register_error_handlers(app)

app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(me.router, prefix="/api/v1")
app.include_router(books.router, prefix="/api/v1")
app.include_router(catalog.router, prefix="/api/v1")
app.include_router(insights.groups_router, prefix="/api/v1")
app.include_router(insights.router, prefix="/api/v1")
app.include_router(ai_proposals.router, prefix="/api/v1")
