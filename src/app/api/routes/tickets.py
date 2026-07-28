"""Ticket browsing (``GET /tickets``) and deletion (``DELETE /tickets/{id}``).

Read-only listing is pure SQL (no LLM): filters narrow the *issues*; a ticket is
returned only when at least one of its issues matches, and only the matching
issues are nested inside it. Deletion removes the ticket and (by DB cascade) its
issues and their embeddings. Both are scoped to the acting user.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.models.ticket import Ticket
from app.schemas.ticket import TicketListResponse
from app.services.stats_cache import invalidate_user_stats
from app.services.tickets import list_tickets

router = APIRouter(tags=["tickets"])


@router.get("/tickets", response_model=TicketListResponse)
def get_tickets(
    user: CurrentUser,
    db: DbSession,
    category: str | None = Query(None, description="bug|feature_request|question|incident|other"),
    severity: str | None = Query(None, description="low|medium|high|critical"),
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
            severity=severity,
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


@router.delete("/tickets/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticket(ticket_id: UUID, user: CurrentUser, db: DbSession) -> None:
    """Delete one of the acting user's tickets (and its issues, via DB cascade).

    404 if the ticket doesn't exist or belongs to another user — the same answer
    either way, so it never reveals that another user's ticket id exists.
    """
    ticket = db.get(Ticket, ticket_id)
    if ticket is None or ticket.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": f"No ticket with id {ticket_id}"},
        )
    db.delete(ticket)
    db.commit()
    # Its issues went with it (DB cascade), so the cached Overview is now wrong.
    invalidate_user_stats(str(user.id))
