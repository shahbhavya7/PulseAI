"""Schemas for weekly summaries and theme aggregation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.schemas.base import APIModel


class ThemeCount(APIModel):
    """A merged theme with how often it occurred and example quotes."""

    theme: str
    count: int
    examples: list[str]  # representative issue quotes (via pgvector similarity)


class SummaryMetrics(APIModel):
    """Numbers computed from the week's issues (all from SQL)."""

    total_issues: int
    by_category: dict[str, int]
    by_severity: dict[str, int]
    needs_review: int
    avg_sentiment: float
    avg_urgency: float


class WeeklySummaryContent(BaseModel):
    """The LLM's structured narrative for a week (grounded themes/metrics are
    computed separately and passed in as context)."""

    model_config = ConfigDict(extra="forbid")

    headline: str  # one punchy line a VP can read at a glance
    narrative: str  # a few sentences: what happened, what matters, what's trending
    recommendations: list[str]  # concrete, actionable next steps


class SummaryResponse(APIModel):
    """Full weekly-summary payload returned by the API."""

    week: str
    status: str
    issue_count: int
    headline: str
    narrative: str
    recommendations: list[str]
    themes: list[ThemeCount]
    metrics: SummaryMetrics
