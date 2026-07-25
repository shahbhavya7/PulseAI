"""Edge cases: AI output schemas (clamping, theme tidying, validation).

Covers schemas/ai.py.
"""

from __future__ import annotations

from app.models.enums import IssueCategory
from app.schemas.ai import (
    Classification,
    SentimentUrgency,
    Themes,
    TicketAnalysis,
)


def test_confidence_is_clamped_to_unit_range() -> None:
    assert Classification(category=IssueCategory.BUG, confidence=1.7).confidence == 1.0
    assert Classification(category=IssueCategory.BUG, confidence=-0.2).confidence == 0.0


def test_sentiment_and_urgency_are_clamped() -> None:
    su = SentimentUrgency(
        sentiment_score=-9.0,
        sentiment_label="negative",  # type: ignore[arg-type]
        urgency_score=5.0,
        urgency_label="critical",  # type: ignore[arg-type]
    )
    assert su.sentiment_score == -1.0
    assert su.urgency_score == 1.0


def test_themes_are_trimmed_lowercased_deduped_and_capped() -> None:
    themes = Themes(labels=["  Photo-Upload Crash ", "photo-upload crash", "", "X"])
    assert themes.labels == ["photo-upload crash", "x"]
    # Cap at 8.
    many = Themes(labels=[f"theme-{i}" for i in range(20)])
    assert len(many.labels) == 8


def test_ticket_analysis_round_trips_json() -> None:
    original = TicketAnalysis(
        issues=[
            {  # type: ignore[list-item]
                "is_valid_ticket": True,
                "summary": "App crashes on photo upload",
                "classification": {"category": "bug", "confidence": 0.9},
                "sentiment_urgency": {
                    "sentiment_score": -0.6,
                    "sentiment_label": "negative",
                    "urgency_score": 0.8,
                    "urgency_label": "high",
                },
                "themes": {"labels": ["photo-upload crash"]},
            }
        ]
    )
    dumped = original.model_dump_json()
    assert TicketAnalysis.model_validate_json(dumped) == original
