"""Weekly summariser: one LLM brief per (user, ISO week).

`generate_summary` gathers **only** the selected week's issues, computes metrics
from them, aggregates themes (grounded with pgvector examples), asks the LLM for
a VP-actionable narrative, and upserts a single `WeeklySummary` row for that
`(user, week)`. `get_summary` reads it back; `to_response` shapes the API
payload straight from the stored row (no recompute).
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.enums import SummaryStatus
from app.models.issue import Issue
from app.models.user import User
from app.models.weekly_summary import WeeklySummary
from app.schemas.summary import (
    SummaryMetrics,
    SummaryResponse,
    ThemeCount,
    WeeklySummaryContent,
)
from app.services import llm
from app.services.insights import aggregate_themes, issues_for_period
from app.services.vector_store import VectorStore

logger = get_logger(__name__)

# summarizer(context) -> WeeklySummaryContent. Injected in tests.
Summarizer = Callable[[str], WeeklySummaryContent]

_MAX_ISSUES_IN_PROMPT = 80


class NoIssuesForWeekError(Exception):
    """Raised when a week has no issues to summarize."""

    def __init__(self, week: str) -> None:
        super().__init__(f"No issues found for week {week}.")
        self.week = week


def _metrics(issues: list[Issue]) -> SummaryMetrics:
    """Compute headline metrics from the week's issues."""
    total = len(issues)
    by_category: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    needs_review = 0
    sentiment_sum = 0.0
    urgency_sum = 0.0
    for issue in issues:
        by_category[issue.category] = by_category.get(issue.category, 0) + 1
        by_severity[issue.severity] = by_severity.get(issue.severity, 0) + 1
        needs_review += 1 if issue.needs_manual_review else 0
        sentiment_sum += issue.sentiment_score
        urgency_sum += issue.urgency_score
    denom = total or 1
    return SummaryMetrics(
        total_issues=total,
        by_category=by_category,
        by_severity=by_severity,
        needs_review=needs_review,
        avg_sentiment=round(sentiment_sum / denom, 3),
        avg_urgency=round(urgency_sum / denom, 3),
    )


def _build_context(issues: list[Issue], metrics: SummaryMetrics, themes: list[ThemeCount]) -> str:
    """Render the week's data as text for the LLM (issues are DATA, capped)."""
    lines = [f"Total issues this week: {metrics.total_issues}"]
    lines.append(f"By category: {metrics.by_category}")
    lines.append(f"By severity: {metrics.by_severity}")
    lines.append(
        f"Needs manual review: {metrics.needs_review}; "
        f"avg sentiment: {metrics.avg_sentiment}; avg urgency: {metrics.avg_urgency}"
    )
    lines.append("\nTop themes (theme × count):")
    lines += [f"- {t.theme} × {t.count}" for t in themes]
    lines.append("\nIssue summaries:")
    lines += [
        f"- [{i.category}/{i.severity}] {(i.description or i.title)}"
        for i in issues[:_MAX_ISSUES_IN_PROMPT]
    ]
    if len(issues) > _MAX_ISSUES_IN_PROMPT:
        lines.append(f"...and {len(issues) - _MAX_ISSUES_IN_PROMPT} more.")
    return "\n".join(lines)


def generate_summary(
    db: Session,
    user: User,
    week: str,
    *,
    summarizer: Summarizer | None = None,
    vector_store: VectorStore | None = None,
) -> WeeklySummary:
    """Generate (or regenerate) and persist the summary for ``(user, week)``.

    Raises:
        NoIssuesForWeekError: If the week has no issues.
        LLMError: If the model call fails (route degrades to 503).
    """
    issues = issues_for_period(db, user.id, week)
    if not issues:
        raise NoIssuesForWeekError(week)

    metrics = _metrics(issues)
    themes = aggregate_themes(db, user.id, week=week, vector_store=vector_store, issues=issues)
    context = _build_context(issues, metrics, themes)

    summarizer = summarizer or llm.summarize_week
    content = summarizer(context)  # may raise LLMError

    summary = db.scalar(
        select(WeeklySummary).where(WeeklySummary.user_id == user.id, WeeklySummary.week == week)
    )
    if summary is None:
        summary = WeeklySummary(user_id=user.id, week=week)
        db.add(summary)

    summary.status = SummaryStatus.COMPLETE
    # `content` (Text column) keeps the joined bullets so plain-text consumers and
    # older rows still work; the structured bullets live in `stats`.
    summary.content = "\n".join(content.highlights)
    summary.issue_count = metrics.total_issues
    summary.stats = {
        "headline": content.headline,
        "highlights": content.highlights,
        "recommendations": content.recommendations,
        "themes": [t.model_dump() for t in themes],
        "metrics": metrics.model_dump(),
    }
    db.commit()
    db.refresh(summary)
    logger.info("Summarized week %s for user %s (%d issues)", week, user.id, metrics.total_issues)
    return summary


def get_summary(db: Session, user: User, week: str) -> WeeklySummary | None:
    """Return the stored summary for ``(user, week)``, or None."""
    return db.scalar(
        select(WeeklySummary).where(WeeklySummary.user_id == user.id, WeeklySummary.week == week)
    )


def to_response(summary: WeeklySummary) -> SummaryResponse:
    """Shape a stored summary row into the API response."""
    stats = summary.stats or {}
    content = summary.content or ""
    # Prefer structured bullets; fall back to splitting the joined text (legacy).
    highlights = stats.get("highlights") or [ln for ln in content.splitlines() if ln.strip()]
    return SummaryResponse(
        week=summary.week,
        status=str(summary.status),
        issue_count=summary.issue_count,
        headline=stats.get("headline", ""),
        highlights=highlights,
        narrative=content,
        recommendations=stats.get("recommendations", []),
        themes=[ThemeCount(**t) for t in stats.get("themes", [])],
        metrics=SummaryMetrics(**stats["metrics"])
        if stats.get("metrics")
        else SummaryMetrics(
            total_issues=summary.issue_count,
            by_category={},
            by_severity={},
            needs_review=0,
            avg_sentiment=0.0,
            avg_urgency=0.0,
        ),
    )
