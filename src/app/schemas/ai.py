"""Pydantic schemas for the AI analysis of a ticket.

These models are the **contract** for the LLM's structured output: the OpenAI
call is told to return exactly a :class:`TicketAnalysis`, so the SDK validates the
JSON against these classes before we ever see it. They double as the internal
result type the pipeline persists.

Design notes
------------
* No ``Field(ge=..., le=...)`` bounds are declared, because those become JSON
  Schema keywords that structured-output strict mode may reject. Instead we
  **clamp** numbers into range with validators, which keeps stored values sane
  even if the model returns something slightly off.
* Every field is required (no defaults) so the strict schema sent to OpenAI marks
  them all required. The skip-the-LLM path builds instances in Python and simply
  supplies every field.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import IssueCategory
from app.schemas.base import APIModel


class SentimentLabel(StrEnum):
    """Coarse sentiment bucket accompanying the numeric score."""

    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"


class UrgencyLabel(StrEnum):
    """Coarse urgency bucket accompanying the numeric score."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class _AIModel(BaseModel):
    """Base for AI output models: reject unexpected keys."""

    model_config = ConfigDict(extra="forbid")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class Classification(_AIModel):
    """What kind of issue this is, and how sure the model is."""

    category: IssueCategory
    confidence: float  # 0..1

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, v: float) -> float:
        return _clamp(v, 0.0, 1.0)


class SentimentUrgency(_AIModel):
    """Sentiment and urgency scored from the FACTS reported, not the tone.

    A calm message describing data loss is high urgency; an angry message about a
    typo is low urgency. Scores are the source of truth; labels summarize them.
    """

    sentiment_score: float  # -1 (very negative) .. 1 (very positive)
    sentiment_label: SentimentLabel
    urgency_score: float  # 0 (no urgency) .. 1 (drop-everything)
    urgency_label: UrgencyLabel

    @field_validator("sentiment_score")
    @classmethod
    def _clamp_sentiment(cls, v: float) -> float:
        return _clamp(v, -1.0, 1.0)

    @field_validator("urgency_score")
    @classmethod
    def _clamp_urgency(cls, v: float) -> float:
        return _clamp(v, 0.0, 1.0)


class Themes(_AIModel):
    """Specific, reusable theme labels (e.g. ``"photo-upload crash"``).

    Never vague buckets like ``"customer issues"``. Labels are trimmed, de-duped,
    and capped so a single issue can't explode into dozens.
    """

    labels: list[str]

    @field_validator("labels")
    @classmethod
    def _tidy(cls, v: list[str]) -> list[str]:
        seen: list[str] = []
        for label in v:
            cleaned = label.strip().lower()
            if cleaned and cleaned not in seen:
                seen.append(cleaned)
        return seen[:8]


class IssueAnalysis(_AIModel):
    """The full analysis of one distinct issue split out of a ticket."""

    summary: str  # one-line description of THIS issue, in your own words
    classification: Classification
    sentiment_urgency: SentimentUrgency
    themes: Themes


class TicketAnalysis(_AIModel):
    """The LLM's answer for one ticket: one or more analyzed issues.

    ``issues`` has length ``1..N`` — the multi-issue fan-out. One ticket about
    both a crash and a billing error yields two entries.
    """

    issues: list[IssueAnalysis]


# ---------------------------------------------------------------------------
# API request/response models for the /analyze endpoints
# ---------------------------------------------------------------------------


class AnalyzeRequest(APIModel):
    """Body for ``POST /analyze``: raw ticket text to analyze."""

    text: str


class AnalyzeResponse(APIModel):
    """Response for ``POST /analyze`` (analysis only, nothing persisted)."""

    source: str  # "cache" | "llm" | "skipped_junk"
    content_hash: str
    flags: list[str]
    analysis: TicketAnalysis


class AnalyzedIssueOut(APIModel):
    """One persisted issue produced by analyzing a ticket."""

    issue_id: UUID
    category: IssueCategory
    severity: str
    confidence: float
    sentiment_score: float
    urgency_score: float
    themes: list[str]
    needs_manual_review: bool


class TicketAnalyzeResponse(APIModel):
    """Response for ``POST /tickets/{id}/analyze`` (fan-out persisted)."""

    ticket_id: UUID
    source: str
    created: int
    issues: list[AnalyzedIssueOut]
