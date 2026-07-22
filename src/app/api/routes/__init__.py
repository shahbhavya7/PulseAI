"""Route modules and the aggregate API router."""

from fastapi import APIRouter

from app.api.routes import health, uploads

# Aggregate router mounted by ``app.main``. Add future routers here.
api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(uploads.router)

__all__ = ["api_router"]
