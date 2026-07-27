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


class WeekSeverityPoint(APIModel):
    """Issue counts split by severity for one ISO week.

    Powers the week-over-week comparison chart, so each bucket is a separate
    field rather than a dict: the chart stacks them and a missing bucket must
    read as 0, not as an absent key.
    """

    week: str
    low: int
    medium: int
    high: int
    critical: int
    total: int


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
    # Per-week severity split, oldest first. Deliberately NOT narrowed by the
    # `week` filter: a week-over-week comparison needs every week available so
    # the UI can offer "last 2 / 3 / all weeks" without refetching.
    weekly_severity: list[WeekSeverityPoint]
