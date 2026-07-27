"""End-to-end Phase 3 tests (require Postgres): analyze → summary → stats.

Each test authenticates as a fresh isolated user (via the ``as_user`` fixture) so
aggregates are deterministic. The model + embeddings are monkeypatched — no
OpenAI key needed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_sessionmaker
from app.models.user import User
from app.schemas.ai import (
    Classification,
    IssueAnalysis,
    SentimentUrgency,
    Themes,
    TicketAnalysis,
)
from app.schemas.summary import WeeklySummaryContent
from app.services import llm, pipeline
from app.services.ingestion import iso_week

pytestmark = pytest.mark.usefixtures("require_db")


def _new_user() -> str:
    with get_sessionmaker()() as db:
        user = User(email=f"{uuid4().hex}@test.local", full_name="Insights Tester")
        db.add(user)
        db.commit()
        return str(user.id)


def _two_issues(_text: str) -> TicketAnalysis:
    def mk(summary: str, category: str, urgency: str, theme: str) -> IssueAnalysis:
        return IssueAnalysis(
            is_valid_ticket=True,
            summary=summary,
            classification=Classification(category=category, confidence=0.9),  # type: ignore[arg-type]
            sentiment_urgency=SentimentUrgency(
                sentiment_score=-0.5,
                sentiment_label="negative",  # type: ignore[arg-type]
                urgency_score=0.9,
                urgency_label=urgency,  # type: ignore[arg-type]
            ),
            themes=Themes(labels=[theme]),
        )

    return TicketAnalysis(
        issues=[
            mk("App crashes on photo upload", "bug", "high", "photo-upload crash"),
            mk("Charged twice at checkout", "incident", "critical", "duplicate-charge billing"),
        ]
    )


class _FakeStore:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.01] * 1536 for _ in texts]

    def embed_one(self, text: str) -> list[float]:
        return [0.01] * 1536


def _fake_summary(_context: str) -> WeeklySummaryContent:
    return WeeklySummaryContent(
        headline="Uploads and billing are the week's pain points",
        highlights=[
            "A photo-upload crash was the top bug this week",
            "A duplicate charge drove a billing incident",
        ],
        recommendations=["Fix the photo-upload crash", "Audit the double-charge path"],
    )


def _analyze_ticket(client: TestClient, text: str) -> None:
    data = (f"text\n{text}\n").encode()
    up = client.post("/uploads", files={"file": ("t.csv", data, "text/csv")})
    assert up.status_code == 201, up.text
    tid = up.json()["created_items"][0]["ticket_id"]
    an = client.post(f"/tickets/{tid}/analyze")
    assert an.status_code == 200, an.text
    assert an.json()["created"] == 2


def test_upload_to_summary_to_stats(
    client: TestClient, as_user: Callable[[str], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(llm, "analyze_ticket_text", _two_issues)
    monkeypatch.setattr(pipeline, "get_vector_store", _FakeStore)
    monkeypatch.setattr(llm, "summarize_week", _fake_summary)

    as_user(_new_user())
    _analyze_ticket(client, f"crash and double charge {uuid4().hex}")
    week = iso_week()

    # Generate the weekly summary (fed only this week's issues).
    gen = client.post(f"/summaries/{week}")
    assert gen.status_code == 200, gen.text
    body = gen.json()
    assert body["headline"]
    assert body["issue_count"] == 2
    assert body["metrics"]["total_issues"] == 2
    assert body["metrics"]["by_category"] == {"bug": 1, "incident": 1}
    # Theme labels are canonicalised so variants aggregate: "photo-upload crash"
    # folds to "app crash", "duplicate-charge billing" to "duplicate charge".
    assert {t["theme"] for t in body["themes"]} == {
        "app crash",
        "duplicate charge",
    }
    # The weekly summary is returned as scannable bullet points, not one para.
    assert body["highlights"] == [
        "A photo-upload crash was the top bug this week",
        "A duplicate charge drove a billing incident",
    ]

    # Read it back.
    got = client.get(f"/summaries/{week}")
    assert got.status_code == 200
    assert got.json()["highlights"] == body["highlights"]
    assert got.json()["narrative"] == body["narrative"]

    # Dashboard stats (SQL), scoped to this user + week.
    stats = client.get(f"/stats?week={week}").json()
    assert stats["total_issues"] == 2
    assert stats["category_distribution"] == {"bug": 1, "incident": 1}
    assert stats["urgency_counts"] == {"high": 1, "critical": 1}
    assert len(stats["sentiment_over_time"]) == 1
    assert stats["sentiment_over_time"][0]["issue_count"] == 2


def test_weekly_severity_ignores_the_week_filter(
    client: TestClient, as_user: Callable[[str], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The comparison series must span all weeks even when a week is selected.

    Narrowing it to the filtered week would leave the week-over-week chart with
    a single bar and nothing to compare against.
    """
    monkeypatch.setattr(llm, "analyze_ticket_text", _two_issues)
    monkeypatch.setattr(pipeline, "get_vector_store", _FakeStore)

    as_user(_new_user())
    _analyze_ticket(client, f"crash and double charge {uuid4().hex}")
    week = iso_week()

    stats = client.get(f"/stats?week={week}").json()

    # The filtered aggregate narrows to the selected week …
    assert stats["total_issues"] == 2
    # … but the comparison series still reports that week in full.
    series = stats["weekly_severity"]
    assert len(series) >= 1
    point = next(p for p in series if p["week"] == week)
    assert point["total"] == 2
    # Severity buckets are explicit fields: an absent bucket is 0, never missing.
    assert point["high"] == 1
    assert point["critical"] == 1
    assert point["low"] == 0
    assert point["medium"] == 0
    assert point["total"] == point["low"] + point["medium"] + point["high"] + point["critical"]


def test_stats_filter_needs_manual_review(
    client: TestClient, as_user: Callable[[str], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(llm, "analyze_ticket_text", _two_issues)
    monkeypatch.setattr(pipeline, "get_vector_store", _FakeStore)
    as_user(_new_user())
    _analyze_ticket(client, f"the checkout page keeps failing on submit case {uuid4().hex}")
    week = iso_week()
    # confidence 0.9 → not flagged for review, so this filter yields zero.
    stats = client.get(f"/stats?week={week}&needs_manual_review=true").json()
    assert stats["total_issues"] == 0


def test_summary_no_issues_returns_404(client: TestClient, as_user: Callable[[str], str]) -> None:
    as_user(_new_user())
    resp = client.post("/summaries/2000-W01")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "no_issues"


def test_data_is_isolated_between_users(
    client: TestClient, as_user: Callable[[str], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """User A's analysed issues must never appear in user B's stats."""
    monkeypatch.setattr(llm, "analyze_ticket_text", _two_issues)
    monkeypatch.setattr(pipeline, "get_vector_store", _FakeStore)
    week = iso_week()

    as_user(_new_user())
    _analyze_ticket(client, f"user-a crash and double charge {uuid4().hex}")
    a_stats = client.get(f"/stats?week={week}").json()
    assert a_stats["total_issues"] == 2

    # Switch to a brand-new user: they see none of user A's data.
    as_user(_new_user())
    b_stats = client.get(f"/stats?week={week}").json()
    assert b_stats["total_issues"] == 0
    assert client.get("/tickets").json()["total"] == 0


def test_embeddings_written_not_marked_reembed(
    client: TestClient, as_user: Callable[[str], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(llm, "analyze_ticket_text", _two_issues)
    monkeypatch.setattr(pipeline, "get_vector_store", _FakeStore)
    uid = as_user(_new_user())
    _analyze_ticket(client, f"the search results load very slowly for query {uuid4().hex}")

    from uuid import UUID

    from sqlalchemy import select

    from app.models.issue import Issue
    from app.models.ticket import Ticket

    with get_sessionmaker()() as db:
        rows: Any = db.execute(
            select(Issue.needs_reembed, Issue.embedding.is_not(None))
            .join(Ticket, Issue.ticket_id == Ticket.id)
            .where(Ticket.owner_id == UUID(uid))
        ).all()
    assert rows and all(not needs and has_vec for needs, has_vec in rows)
