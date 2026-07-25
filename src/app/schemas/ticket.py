"""Schemas for the ``GET /tickets`` browse endpoint.

Returns the acting user's tickets, each with its analyzed issues nested inside,
so the dashboard can group issues by ticket and badge multi-issue tickets.
Filters narrow the *issues* considered; a ticket appears only if at least one of
its issues matches the active filters.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.models.enums import IssueCategory, IssueSeverity
from app.schemas.base import APIModel


class IssueOut(APIModel):
    """One analyzed issue as shown in the tickets browser."""

    id: UUID
    title: str
    category: IssueCategory
    severity: IssueSeverity
    confidence: float
    sentiment_score: float
    urgency_score: float
    themes: list[str]
    needs_manual_review: bool
    flags: list[str]
    analyzed_at: datetime | None
    created_at: datetime


class TicketOut(APIModel):
    """A ticket with its (filtered) issues nested inside."""

    id: UUID
    title: str
    body: str  # the stored raw ticket text (cleaned + PII-redacted)
    source: str
    status: str
    created_at: datetime
    issue_count: int  # number of issues shown (after filtering)
    issues: list[IssueOut]


class TicketListResponse(APIModel):
    """Paged list of tickets for the acting user."""

    total: int  # total tickets matching the filters (before limit/offset)
    limit: int
    offset: int
    tickets: list[TicketOut]
