"""AI analysis endpoints.

* ``POST /analyze`` — analyze raw text and return the structured result
  (clean → cache → skip-junk/LLM → validate). Nothing is persisted, so it's the
  simplest way to exercise the pipeline (idempotency, injection, empty input).
* ``POST /tickets/{ticket_id}/analyze`` — analyze a stored ticket and persist the
  multi-issue fan-out.

Both map AI failures (missing key / API error) to a clean **503**, never a crash.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.models.ticket import Ticket
from app.schemas.ai import (
    AnalyzedIssueOut,
    AnalyzeRequest,
    AnalyzeResponse,
    TicketAnalyzeResponse,
)
from app.services.llm import LLMError
from app.services.pipeline import analyze, analyze_and_persist

router = APIRouter(tags=["analyze"])


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze_text(payload: AnalyzeRequest, user: CurrentUser) -> AnalyzeResponse:
    """Analyze raw ticket text and return the structured analysis."""
    try:
        outcome = analyze(payload.text, user_id_str=str(user.id))
    except LLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "ai_unavailable", "message": exc.message},
        ) from exc
    return AnalyzeResponse(
        source=outcome.source.value,
        content_hash=outcome.content_hash,
        flags=outcome.flags,
        analysis=outcome.analysis,
    )


@router.post("/tickets/{ticket_id}/analyze", response_model=TicketAnalyzeResponse)
def analyze_ticket(ticket_id: UUID, user: CurrentUser, db: DbSession) -> TicketAnalyzeResponse:
    """Analyze a stored ticket and persist the fanned-out issues."""
    ticket = db.get(Ticket, ticket_id)
    if ticket is None or ticket.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No ticket with id {ticket_id}",
        )
    try:
        issues = analyze_and_persist(db, ticket)
    except LLMError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "ai_unavailable", "message": exc.message},
        ) from exc
    return TicketAnalyzeResponse(
        ticket_id=ticket.id,
        source="persisted",
        created=len(issues),
        issues=[
            AnalyzedIssueOut(
                issue_id=i.id,
                category=i.category,
                severity=str(i.severity),
                confidence=i.confidence,
                sentiment_score=i.sentiment_score,
                urgency_score=i.urgency_score,
                themes=i.themes,
                needs_manual_review=i.needs_manual_review,
            )
            for i in issues
        ],
    )
