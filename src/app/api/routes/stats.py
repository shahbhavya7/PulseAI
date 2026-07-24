"""Dashboard stats endpoint (`GET /stats`).

Pure SQL aggregation for the acting user, filterable by week / minimum
confidence / needs_manual_review. No LLM involved, so it always works.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.stats import StatsResponse
from app.services.stats import compute_stats

router = APIRouter(tags=["stats"])


@router.get("/stats", response_model=StatsResponse)
def get_stats(
    user: CurrentUser,
    db: DbSession,
    week: str | None = Query(None, description="ISO week, e.g. 2026-W30"),
    min_confidence: float | None = Query(None, ge=0.0, le=1.0),
    needs_manual_review: bool | None = Query(None),
) -> StatsResponse:
    """Return dashboard aggregates under the given filters."""
    return compute_stats(
        db,
        user.id,
        week=week,
        min_confidence=min_confidence,
        needs_manual_review=needs_manual_review,
    )
