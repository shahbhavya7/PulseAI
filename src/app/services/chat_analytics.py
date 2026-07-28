"""Natural-language analytics for chat: question -> safe SQL -> rows.

This is the "ask a real question, get a real number" path. The standard chat
context carries pre-computed metrics, but those are fixed aggregates: they
cannot answer "how many critical issues this week versus last week". Here the
model writes a query for exactly what was asked.

The flow, and where the trust boundary sits::

    question
      -> llm.generate_analytics_sql   (UNTRUSTED output)
      -> sql_guard.validate_sql       (the boundary: allowlist + denylist)
      -> sql_guard.run_readonly_query (READ ONLY txn, always rolled back)
      -> rendered rows for the prompt + a table for the UI

Every failure degrades to "no analytics block" rather than raising, because a
bad generated query must never break the chat answer: the assistant simply falls
back to the standard metrics it already has.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.schemas.analytics import (
    AnalyticsChart,
    AnalyticsTable,
    ChartKind,
    ChartPoint,
    ChartSeries,
)
from app.services import llm
from app.services.llm import LLMError
from app.services.sql_guard import QueryResult, SQLGuardError, run_readonly_query

logger = get_logger(__name__)

# Cap on rows fed back into the prompt. Comparison answers are small by nature;
# this stops a wide GROUP BY from eating the context window.
_MAX_PROMPT_ROWS = 25


# Charts stay readable past this many slices/bars; a pie especially becomes
# unreadable well before this, but even a bar chart is noise past a few dozen.
_MAX_CHART_POINTS = 30


@dataclass
class AnalyticsOutcome:
    """Result of the analytics attempt for one question."""

    # The SQL that actually ran (post-validation), or None if nothing ran.
    sql: str | None = None
    explanation: str = ""
    result: QueryResult | None = None
    chart_kind: ChartKind = ChartKind.NONE
    chart_label_column: str = ""
    chart_value_columns: list[str] = field(default_factory=list)
    # Set when we tried and could not produce an answer, for logging/telemetry.
    error: str | None = None

    @property
    def has_data(self) -> bool:
        return self.result is not None and not self.result.is_empty

    def as_table(self) -> AnalyticsTable | None:
        """Render for the API response, so the UI can show a real table."""
        if self.result is None or self.result.is_empty:
            return None
        return AnalyticsTable(
            columns=self.result.columns,
            rows=self.result.rows,
            truncated=self.result.truncated,
        )

    def as_chart(self) -> AnalyticsChart | None:
        """Build a chart spec from the result, or None if no chart applies.

        Guards against the model naming a column it didn't actually select, or
        a value column that isn't numeric — either just means no chart, never
        an error surfaced to the user (the table still renders either way).
        One :class:`ChartSeries` per requested value column, so comparing two
        severities produces two series on one chart, not just the first.
        """
        if self.chart_kind is ChartKind.NONE or self.result is None or self.result.is_empty:
            return None
        cols = self.result.columns
        # A pie is single-series by construction; extra columns are ignored
        # rather than rejected, since the model may over-list out of caution.
        value_columns = (
            self.chart_value_columns[:1]
            if self.chart_kind is ChartKind.PIE
            else self.chart_value_columns
        )

        if self.chart_label_column not in cols or not value_columns:
            logger.info(
                "Chart label/value columns invalid (label=%s values=%s cols=%s); skipping chart",
                self.chart_label_column,
                value_columns,
                cols,
            )
            return None
        label_idx = cols.index(self.chart_label_column)

        series: list[ChartSeries] = []
        for value_col in value_columns:
            if value_col not in cols:
                logger.info("Chart value column %s not in result; skipping it", value_col)
                continue
            value_idx = cols.index(value_col)
            points: list[ChartPoint] = []
            for row in self.result.rows[:_MAX_CHART_POINTS]:
                value = row[value_idx]
                if not isinstance(value, int | float) or isinstance(value, bool):
                    logger.info("Chart value column %s is not numeric; skipping it", value_col)
                    points = []
                    break
                points.append(ChartPoint(label=str(row[label_idx]), value=float(value)))
            if points:
                series.append(ChartSeries(name=value_col, points=points))

        if not series:
            return None
        return AnalyticsChart(
            kind=self.chart_kind,
            label_column=self.chart_label_column,
            series=series,
        )


def current_iso_week(now: datetime | None = None) -> str:
    """Return the current ISO week bucket ("YYYY-Www"), matching Issue.week."""
    moment = now or datetime.now(UTC)
    year, week, _ = moment.isocalendar()
    return f"{year}-W{week:02d}"


def _is_id_column(name: str) -> bool:
    """True for opaque identifier columns (uuids and the like)."""
    lowered = name.lower()
    return lowered == "id" or lowered.endswith("_id")


def _render_rows(result: QueryResult) -> str:
    """Render rows as a compact text table the model can read and quote.

    Identifier columns are dropped: a uuid means nothing to a reader, and
    including them invites the model to transcribe them into the answer. The
    UI still receives the full result set.
    """
    keep = [i for i, c in enumerate(result.columns) if not _is_id_column(c)]
    if not keep:  # a query that selected only ids: keep them rather than nothing
        keep = list(range(len(result.columns)))

    header = " | ".join(result.columns[i] for i in keep)
    separator = "-" * len(header)
    lines = [header, separator]
    for row in result.rows[:_MAX_PROMPT_ROWS]:
        cells = []
        for i in keep:
            value = row[i]
            if isinstance(value, float):
                cells.append(f"{value:.2f}")
            else:
                cells.append("null" if value is None else str(value))
        lines.append(" | ".join(cells))
    if result.truncated or len(result.rows) > _MAX_PROMPT_ROWS:
        lines.append("(results truncated)")
    return "\n".join(lines)


def format_for_prompt(outcome: AnalyticsOutcome) -> str | None:
    """Render the outcome as a context block, or None when no query ran.

    A query that ran and matched nothing still produces a block. "Zero for this
    period" is a true, useful answer, and stating it explicitly stops the model
    from falling back to the standing metrics and reporting an unrelated total
    as if it were the answer.
    """
    if outcome.result is None:
        return None
    if outcome.result.is_empty:
        return (
            "LIVE QUERY RESULT (run against the user's data just now, for: "
            f"{outcome.explanation}): NO ROWS MATCHED. The correct answer is "
            "that there are none for what was asked. Say so plainly. Do NOT "
            "substitute totals from the metrics above, which cover a different "
            "scope and would be wrong here."
        )
    return (
        "LIVE QUERY RESULT (exact numbers computed from the user's data just "
        f"now, for: {outcome.explanation}):\n{_render_rows(outcome.result)}"
    )


def run_analytics(
    db: Session,
    user_id: UUID,
    question: str,
    *,
    now: datetime | None = None,
) -> AnalyticsOutcome:
    """Attempt to answer ``question`` with a generated read-only query.

    Never raises. Any failure (model down, unsafe SQL, bad query) returns an
    outcome with ``error`` set and no data, so the caller just omits the block.
    """
    moment = now or datetime.now(UTC)
    week = current_iso_week(moment)

    try:
        plan = llm.generate_analytics_sql(question, current_week=week, now_iso=moment.isoformat())
    except LLMError as exc:
        logger.info("Analytics SQL generation unavailable: %s", exc)
        return AnalyticsOutcome(error=str(exc))

    if not plan.needs_query or not plan.sql.strip():
        return AnalyticsOutcome()

    try:
        result = run_readonly_query(db, plan.sql, user_id, now=moment)
    except SQLGuardError as exc:
        # A rejected query is a notable event: either the model drifted or
        # something tried to make it write. Logged with the offending SQL.
        logger.warning("Rejected generated SQL (%s): %s", exc.reason, plan.sql)
        return AnalyticsOutcome(explanation=plan.explanation, error=exc.reason)

    logger.info("Analytics query ran for user=%s rows=%d", user_id, len(result.rows))
    return AnalyticsOutcome(
        sql=plan.sql,
        explanation=plan.explanation,
        result=result,
        chart_kind=plan.chart,
        chart_label_column=plan.chart_label_column,
        chart_value_columns=plan.chart_value_columns,
    )
