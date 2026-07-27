"""Schemas for the natural-language SQL analytics path in chat.

:class:`AnalyticsPlan` is the LLM's structured output when it is asked whether a
chat question needs a real database query. Keeping the decision *and* the SQL in
one strict schema means the model has to commit to both at once, and we can
reject the whole thing if either half looks wrong.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


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


class AnalyticsTable(BaseModel):
    """A rendered result set attached to a chat answer."""

    columns: list[str]
    rows: list[list[Any]]
    truncated: bool = False
