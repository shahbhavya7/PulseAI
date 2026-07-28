"""Schemas for the natural-language SQL analytics path in chat.

:class:`AnalyticsPlan` is the LLM's structured output when it is asked whether a
chat question needs a real database query. Keeping the decision *and* the SQL in
one strict schema means the model has to commit to both at once, and we can
reject the whole thing if either half looks wrong.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class ChartKind(StrEnum):
    """How a result set should be drawn, if at all.

    The model picks this alongside the SQL, because only it knows whether the
    user asked for a comparison ("bar"), a composition ("pie"), a movement over
    time ("line"), or just a number ("none"). Rule-based inference in code
    cannot honour an explicit "show me a pie chart".
    """

    NONE = "none"
    BAR = "bar"
    PIE = "pie"
    LINE = "line"


class AnalyticsPlan(BaseModel):
    """The model's decision about whether to run SQL, plus the SQL itself."""

    model_config = ConfigDict(extra="forbid")

    # True when the question needs a real aggregation the standard metrics block
    # cannot answer (period comparisons, filtered counts, breakdowns).
    needs_query: bool
    # A single read-only SELECT scoped by :user_id. Empty string when
    # needs_query is False.
    sql: str
    # One short sentence describing what the query computes, shown to the user
    # so the number is never an unexplained black box.
    explanation: str
    # How to draw the result. "none" means the numbers speak for themselves.
    chart: ChartKind
    # The category/week/day axis. Must be a column the SQL actually selects;
    # validated against the result before use.
    chart_label_column: str
    # One or more numeric columns to plot, e.g. ["critical_count"] or
    # ["critical_count", "high_count"] to compare two series on one chart.
    # A pie chart is single-series by construction; extra entries are ignored.
    chart_value_columns: list[str]


class ChartPoint(BaseModel):
    """One labelled datum for one series on a chat-generated chart."""

    label: str
    value: float


class ChartSeries(BaseModel):
    """One value column plotted across every label — one bar colour, one line."""

    name: str
    points: list[ChartPoint]


class AnalyticsChart(BaseModel):
    """A chart spec attached to a chat answer, ready for the UI to render."""

    kind: ChartKind
    label_column: str
    # One series per plotted value column. Multiple series render as grouped
    # bars or multiple lines; a pie chart only ever has one.
    series: list[ChartSeries]


class AnalyticsTable(BaseModel):
    """A rendered result set attached to a chat answer."""

    columns: list[str]
    rows: list[list[Any]]
    truncated: bool = False
