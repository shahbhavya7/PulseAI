"""Dashboard aggregation — all computed in SQL, filterable.

`compute_stats` returns category distribution, urgency (severity) counts,
sentiment/urgency trend by week, and top themes for the acting user, filtered by
any combination of week / minimum confidence / needs_manual_review. Themes reuse
the aggregation in :mod:`app.services.insights`.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import Select

from app.models.issue import Issue
from app.models.ticket import Ticket
from app.schemas.stats import (
    SentimentPoint,
    StatsFilters,
    StatsResponse,
    WeekSeverityPoint,
)
from app.services.insights import aggregate_themes
from app.services.vector_store import VectorStore


def _base_filters(
    stmt: Select[Any],
    user_id: UUID,
    *,
    week: str | None,
    min_confidence: float | None,
    needs_manual_review: bool | None,
) -> Select[Any]:
    """Apply the shared WHERE clauses (owner + optional filters) to a query."""
    stmt = stmt.join(Ticket, Issue.ticket_id == Ticket.id).where(Ticket.owner_id == user_id)
    if week is not None:
        stmt = stmt.where(Issue.week == week)
    if min_confidence is not None:
        stmt = stmt.where(Issue.confidence >= min_confidence)
    if needs_manual_review is not None:
        stmt = stmt.where(Issue.needs_manual_review.is_(needs_manual_review))
    return stmt


def compute_stats(
    db: Session,
    user_id: UUID,
    *,
    week: str | None = None,
    min_confidence: float | None = None,
    needs_manual_review: bool | None = None,
    vector_store: VectorStore | None = None,
) -> StatsResponse:
    """Compute dashboard aggregates for the acting user under the given filters."""

    def filtered(stmt: Select[Any]) -> Select[Any]:
        return _base_filters(
            stmt,
            user_id,
            week=week,
            min_confidence=min_confidence,
            needs_manual_review=needs_manual_review,
        )

    total = db.scalar(filtered(select(func.count(Issue.id)))) or 0

    category_rows = db.execute(
        filtered(select(Issue.category, func.count(Issue.id))).group_by(Issue.category)
    ).all()
    category_distribution = {str(cat): int(n) for cat, n in category_rows}

    urgency_rows = db.execute(
        filtered(select(Issue.severity, func.count(Issue.id))).group_by(Issue.severity)
    ).all()
    urgency_counts = {str(sev): int(n) for sev, n in urgency_rows}

    trend_rows = db.execute(
        filtered(
            select(
                Issue.week,
                func.avg(Issue.sentiment_score),
                func.avg(Issue.urgency_score),
                func.count(Issue.id),
            )
        )
        .group_by(Issue.week)
        .order_by(Issue.week)
    ).all()
    sentiment_over_time = [
        SentimentPoint(
            week=str(wk),
            avg_sentiment=round(float(s or 0.0), 3),
            avg_urgency=round(float(u or 0.0), 3),
            issue_count=int(n),
        )
        for wk, s, u, n in trend_rows
    ]

    # Week-over-week severity split. The `week` filter is intentionally omitted
    # (the other filters still apply): comparing weeks requires every week, and
    # scoping to one would leave the comparison chart with a single bar.
    severity_rows = db.execute(
        _base_filters(
            select(Issue.week, Issue.severity, func.count(Issue.id)),
            user_id,
            week=None,
            min_confidence=min_confidence,
            needs_manual_review=needs_manual_review,
        )
        .group_by(Issue.week, Issue.severity)
        .order_by(Issue.week)
    ).all()

    by_week: dict[str, dict[str, int]] = defaultdict(dict)
    for wk, sev, n in severity_rows:
        by_week[str(wk)][str(sev)] = int(n)
    weekly_severity = [
        WeekSeverityPoint(
            week=wk,
            low=buckets.get("low", 0),
            medium=buckets.get("medium", 0),
            high=buckets.get("high", 0),
            critical=buckets.get("critical", 0),
            total=sum(buckets.values()),
        )
        for wk, buckets in sorted(by_week.items())
    ]

    top_themes = aggregate_themes(db, user_id, week=week, limit=10, vector_store=vector_store)

    return StatsResponse(
        total_issues=int(total),
        filters=StatsFilters(
            week=week,
            min_confidence=min_confidence,
            needs_manual_review=needs_manual_review,
        ),
        category_distribution=category_distribution,
        urgency_counts=urgency_counts,
        sentiment_over_time=sentiment_over_time,
        top_themes=top_themes,
        weekly_severity=weekly_severity,
    )
