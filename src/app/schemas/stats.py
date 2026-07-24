"""Schemas for the dashboard aggregation endpoint (`GET /stats`)."""

from __future__ import annotations

from app.schemas.base import APIModel
from app.schemas.summary import ThemeCount


class SentimentPoint(APIModel):
    """Average sentiment/urgency for one ISO week (a point on the trend line)."""

    week: str
    avg_sentiment: float
    avg_urgency: float
    issue_count: int


class StatsFilters(APIModel):
    """Echo of the filters that produced these stats."""

    week: str | None
    min_confidence: float | None
    needs_manual_review: bool | None


class StatsResponse(APIModel):
    """Dashboard aggregates, all computed in SQL."""

    total_issues: int
    filters: StatsFilters
    category_distribution: dict[str, int]
    urgency_counts: dict[str, int]  # by severity bucket (low/medium/high/critical)
    sentiment_over_time: list[SentimentPoint]
    top_themes: list[ThemeCount]
