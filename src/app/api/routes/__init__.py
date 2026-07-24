"""Route modules and the aggregate API router."""

from fastapi import APIRouter

from app.api.routes import analyze, health, stats, summaries, uploads

# Aggregate router mounted by ``app.main``. Add future routers here.
api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(uploads.router)
api_router.include_router(analyze.router)
api_router.include_router(summaries.router)
api_router.include_router(stats.router)

__all__ = ["api_router"]
