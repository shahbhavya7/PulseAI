"""Integration tests for the browse endpoint ``GET /tickets`` (require Postgres).

Each test uses a fresh isolated user so results are deterministic. The model is
monkeypatched, so no OpenAI key is needed.
"""

from __future__ import annotations

from collections.abc import Callable
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
from app.services import llm, pipeline

pytestmark = pytest.mark.usefixtures("require_db")


def _new_user() -> str:
    with get_sessionmaker()() as db:
        user = User(email=f"{uuid4().hex}@test.local", full_name="Tickets Tester")
        db.add(user)
        db.commit()
        return str(user.id)


def _two_issues(_text: str) -> TicketAnalysis:
    def mk(
        summary: str, category: str, urgency: str, sentiment: float, theme: str
    ) -> IssueAnalysis:
        return IssueAnalysis(
            summary=summary,
            classification=Classification(category=category, confidence=0.9),  # type: ignore[arg-type]
            sentiment_urgency=SentimentUrgency(
                sentiment_score=sentiment,
                sentiment_label="negative" if sentiment < 0 else "positive",  # type: ignore[arg-type]
                urgency_score=0.9,
                urgency_label=urgency,  # type: ignore[arg-type]
            ),
            themes=Themes(labels=[theme]),
        )

    return TicketAnalysis(
        issues=[
            mk("App crashes on photo upload", "bug", "high", -0.6, "photo-upload crash"),
            mk("Loves the new dark mode", "feature_request", "low", 0.7, "dark-mode praise"),
        ]
    )


class _FakeStore:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.01] * 1536 for _ in texts]

    def embed_one(self, text: str) -> list[float]:
        return [0.01] * 1536


def _upload_and_analyze(client: TestClient, text: str) -> str:
    data = (f"text\n{text}\n").encode()
    up = client.post("/uploads", files={"file": ("t.csv", data, "text/csv")})
    assert up.status_code == 201, up.text
    tid = up.json()["created_items"][0]["ticket_id"]
    an = client.post(f"/tickets/{tid}/analyze")
    assert an.status_code == 200, an.text
    return tid


def test_tickets_groups_issues_and_reports_count(
    client: TestClient, as_user: Callable[[str], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(llm, "analyze_ticket_text", _two_issues)
    monkeypatch.setattr(pipeline, "get_vector_store", _FakeStore)
    as_user(_new_user())
    _upload_and_analyze(
        client,
        f"the app keeps crashing on photo upload and I love the new dark mode {uuid4().hex}",
    )

    resp = client.get("/tickets")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    ticket = body["tickets"][0]
    assert ticket["issue_count"] == 2
    assert len(ticket["issues"]) == 2
    cats = {i["category"] for i in ticket["issues"]}
    assert cats == {"bug", "feature_request"}


def test_tickets_category_filter_narrows_nested_issues(
    client: TestClient, as_user: Callable[[str], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(llm, "analyze_ticket_text", _two_issues)
    monkeypatch.setattr(pipeline, "get_vector_store", _FakeStore)
    as_user(_new_user())
    _upload_and_analyze(
        client,
        f"the app keeps crashing on photo upload and I love the new dark mode {uuid4().hex}",
    )

    resp = client.get("/tickets?category=bug")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    ticket = body["tickets"][0]
    # Only the matching (bug) issue is nested, and the badge reflects that.
    assert ticket["issue_count"] == 1
    assert [i["category"] for i in ticket["issues"]] == ["bug"]


def test_tickets_sentiment_filter(
    client: TestClient, as_user: Callable[[str], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(llm, "analyze_ticket_text", _two_issues)
    monkeypatch.setattr(pipeline, "get_vector_store", _FakeStore)
    as_user(_new_user())
    _upload_and_analyze(
        client,
        f"the app keeps crashing on photo upload and I love the new dark mode {uuid4().hex}",
    )

    resp = client.get("/tickets?sentiment=positive")
    assert resp.status_code == 200
    ticket = resp.json()["tickets"][0]
    assert [i["category"] for i in ticket["issues"]] == ["feature_request"]


def test_tickets_invalid_category_is_422(
    client: TestClient, as_user: Callable[[str], str]
) -> None:
    as_user(_new_user())
    resp = client.get("/tickets?category=nonsense")
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "invalid_filter"


def test_tickets_empty_for_new_user(
    client: TestClient, as_user: Callable[[str], str]
) -> None:
    as_user(_new_user())
    resp = client.get("/tickets")
    assert resp.status_code == 200
    assert resp.json() == {"total": 0, "limit": 50, "offset": 0, "tickets": []}


def test_tickets_requires_auth(client: TestClient) -> None:
    # No as_user() → no session → 401 (real auth, no stub fallback).
    resp = client.get("/tickets")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "not_authenticated"
