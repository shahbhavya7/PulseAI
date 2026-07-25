"""Read-side service for browsing tickets with their analyzed issues.

`list_tickets` powers the dashboard's Tickets route: it returns the acting
user's tickets with matching issues nested inside. Filters narrow the *issues*;
a ticket is included only when at least one of its issues survives the filters,
and only the surviving issues are attached (so the UI groups correctly and the
"N issues" badge reflects what is shown).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.enums import IssueCategory
from app.models.issue import Issue
from app.models.ticket import Ticket
from app.schemas.ticket import IssueOut, TicketListResponse, TicketOut

# Sentiment label → inclusive score band. Sentiment is scored -1..1; these bands
# match the coarse labels used elsewhere (see schemas.ai.SentimentLabel).
_SENTIMENT_BANDS: dict[str, tuple[float, float]] = {
    "negative": (-1.0, -0.2),
    "neutral": (-0.2, 0.2),
    "positive": (0.2, 1.0),
}


def _apply_issue_filters(
    stmt: Select[tuple[Issue]],
    *,
    category: str | None,
    sentiment: str | None,
    min_confidence: float | None,
    needs_manual_review: bool | None,
) -> Select[tuple[Issue]]:
    """Apply the issue-level WHERE clauses shared by count and fetch queries."""
    if category is not None:
        stmt = stmt.where(Issue.category == IssueCategory(category))
    if sentiment is not None:
        low, high = _SENTIMENT_BANDS[sentiment]
        stmt = stmt.where(Issue.sentiment_score >= low, Issue.sentiment_score <= high)
    if min_confidence is not None:
        stmt = stmt.where(Issue.confidence >= min_confidence)
    if needs_manual_review is not None:
        stmt = stmt.where(Issue.needs_manual_review.is_(needs_manual_review))
    return stmt


def _to_issue_out(issue: Issue) -> IssueOut:
    return IssueOut(
        id=issue.id,
        title=issue.title,
        category=issue.category,
        severity=issue.severity,
        confidence=issue.confidence,
        sentiment_score=issue.sentiment_score,
        urgency_score=issue.urgency_score,
        themes=list(issue.themes),
        needs_manual_review=issue.needs_manual_review,
        flags=list(issue.flags),
        analyzed_at=issue.analyzed_at,
        created_at=issue.created_at,
    )


def list_tickets(
    db: Session,
    user_id: UUID,
    *,
    category: str | None = None,
    sentiment: str | None = None,
    min_confidence: float | None = None,
    needs_manual_review: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> TicketListResponse:
    """Return the user's tickets (with matching issues nested), newest first."""
    if sentiment is not None and sentiment not in _SENTIMENT_BANDS:
        raise ValueError(f"Unknown sentiment filter: {sentiment!r}")
    if category is not None:
        # Validate early so a bad value is a clean error, not a 500.
        IssueCategory(category)

    # Ticket ids that own at least one issue passing the filters.
    matching_issues: Select[tuple[Issue]] = _apply_issue_filters(
        select(Issue).where(Issue.ticket_id == Ticket.id),
        category=category,
        sentiment=sentiment,
        min_confidence=min_confidence,
        needs_manual_review=needs_manual_review,
    )
    ticket_ids_stmt = (
        select(Ticket.id)
        .where(Ticket.owner_id == user_id)
        .where(matching_issues.exists())
        .order_by(Ticket.created_at.desc())
    )

    total = db.scalar(select(func.count()).select_from(ticket_ids_stmt.subquery())) or 0

    page_ids = list(db.scalars(ticket_ids_stmt.limit(limit).offset(offset)).all())
    if not page_ids:
        return TicketListResponse(total=int(total), limit=limit, offset=offset, tickets=[])

    tickets = list(
        db.scalars(
            select(Ticket).where(Ticket.id.in_(page_ids)).order_by(Ticket.created_at.desc())
        ).all()
    )

    out: list[TicketOut] = []
    for ticket in tickets:
        # Keep only the issues that match the active filters (the badge and the
        # grouping must reflect what the user filtered for).
        shown = [
            iss
            for iss in ticket.issues
            if _issue_matches(
                iss,
                category=category,
                sentiment=sentiment,
                min_confidence=min_confidence,
                needs_manual_review=needs_manual_review,
            )
        ]
        out.append(
            TicketOut(
                id=ticket.id,
                title=ticket.title,
                body=ticket.body or ticket.title,
                source=str(ticket.source),
                status=str(ticket.status),
                created_at=ticket.created_at,
                issue_count=len(shown),
                issues=[_to_issue_out(i) for i in shown],
            )
        )
    return TicketListResponse(total=int(total), limit=limit, offset=offset, tickets=out)


def _issue_matches(
    issue: Issue,
    *,
    category: str | None,
    sentiment: str | None,
    min_confidence: float | None,
    needs_manual_review: bool | None,
) -> bool:
    """In-Python mirror of the SQL filters, applied to a loaded issue."""
    if category is not None and str(issue.category) != category:
        return False
    if sentiment is not None:
        low, high = _SENTIMENT_BANDS[sentiment]
        if not (low <= issue.sentiment_score <= high):
            return False
    if min_confidence is not None and issue.confidence < min_confidence:
        return False
    return not (
        needs_manual_review is not None and issue.needs_manual_review != needs_manual_review
    )
