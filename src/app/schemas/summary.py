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
    """The LLM's structured brief for a week (grounded themes/metrics are
    computed separately and passed in as context)."""

    model_config = ConfigDict(extra="forbid")

    headline: str  # one punchy line a VP can read at a glance
    highlights: list[str]  # 3-6 scannable bullet points: what happened / what matters
    recommendations: list[str]  # concrete, actionable next steps


class SummaryResponse(APIModel):
    """Full weekly-summary payload returned by the API."""

    week: str
    status: str
    issue_count: int
    headline: str
    highlights: list[str]  # the week's key points, as bullets
    narrative: str  # highlights joined into text (legacy/compat + plain fallback)
    recommendations: list[str]
    themes: list[ThemeCount]
    metrics: SummaryMetrics
