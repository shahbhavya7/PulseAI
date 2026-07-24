"""``GET /tickets`` — browse the acting user's tickets with their issues.

Read-only, pure SQL (no LLM). Filters narrow the *issues*; a ticket is returned
only when at least one of its issues matches, and only the matching issues are
nested inside it. This powers the dashboard's Tickets route.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.ticket import TicketListResponse
from app.services.tickets import list_tickets

router = APIRouter(tags=["tickets"])


@router.get("/tickets", response_model=TicketListResponse)
def get_tickets(
    user: CurrentUser,
    db: DbSession,
    category: str | None = Query(None, description="bug|feature_request|question|incident|other"),
    sentiment: str | None = Query(None, description="negative|neutral|positive"),
    min_confidence: float | None = Query(None, ge=0.0, le=1.0),
    needs_manual_review: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> TicketListResponse:
    """List tickets (with matching issues nested), newest first."""
    try:
        return list_tickets(
            db,
            user.id,
            category=category,
            sentiment=sentiment,
            min_confidence=min_confidence,
            needs_manual_review=needs_manual_review,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_filter", "message": str(exc)},
        ) from exc
