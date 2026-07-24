"""Integration tests for the /analyze endpoints (require a live Postgres).

The model call is monkeypatched where a real analysis is needed, so no OpenAI key
is required. Unique text per run avoids Redis cache carry-over between runs.
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
from app.services import llm

pytestmark = pytest.mark.usefixtures("require_db")


@pytest.fixture(autouse=True)
def _auth(require_db: None, as_user: Callable[[str], str]) -> None:
    """Authenticate every analyze test as a fresh, isolated user."""
    with get_sessionmaker()() as db:
        user = User(email=f"{uuid4().hex}@test.local", full_name="Analyze Tester")
        db.add(user)
        db.commit()
        as_user(str(user.id))


def _two_issue_analysis(_text: str) -> TicketAnalysis:
    def issue(summary: str, category: str, urgency: str) -> IssueAnalysis:
        return IssueAnalysis(
            summary=summary,
            classification=Classification(category=category, confidence=0.9),  # type: ignore[arg-type]
            sentiment_urgency=SentimentUrgency(
                sentiment_score=-0.5,
                sentiment_label="negative",  # type: ignore[arg-type]
                urgency_score=0.9,
                urgency_label=urgency,  # type: ignore[arg-type]
            ),
            themes=Themes(labels=[f"{category}-theme"]),
        )

    return TicketAnalysis(
        issues=[
            issue("App crashes on photo upload", "bug", "high"),
            issue("Double charged on checkout", "incident", "critical"),
        ]
    )


# ---- /analyze --------------------------------------------------------------


def test_analyze_empty_is_skipped_junk(client: TestClient) -> None:
    resp = client.post("/analyze", json={"text": ""})
    assert resp.status_code == 200, resp.text
    assert resp.json()["source"] == "skipped_junk"


def test_analyze_junk_is_skipped_junk(client: TestClient) -> None:
    resp = client.post("/analyze", json={"text": "!!!! ???? @@@"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["source"] == "skipped_junk"


def test_analyze_real_text_without_key_degrades_to_503(client: TestClient) -> None:
    # No API key in the test env → graceful 503, never a crash. Unique text so a
    # previously-cached analysis can't turn this into a 200 cache hit.
    llm.get_openai_client.cache_clear()
    resp = client.post(
        "/analyze", json={"text": f"The app crashes every time I log in {uuid4().hex}."}
    )
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "ai_unavailable"


def test_analyze_is_idempotent_via_cache(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"n": 0}

    def fake(text: str) -> TicketAnalysis:
        calls["n"] += 1
        return _two_issue_analysis(text)

    monkeypatch.setattr(llm, "analyze_ticket_text", fake)
    text = f"Checkout returns a 500 error {uuid4().hex}"

    first = client.post("/analyze", json={"text": text}).json()
    second = client.post("/analyze", json={"text": text}).json()

    assert first["source"] == "llm"
    assert second["source"] == "cache"
    assert calls["n"] == 1  # model called once; second served from cache
    assert first["analysis"] == second["analysis"]


# ---- /tickets/{id}/analyze (persisted fan-out) -----------------------------


def _create_ticket(client: TestClient, text: str) -> str:
    data = (f"text\n{text}\n").encode()
    resp = client.post("/uploads", files={"file": ("t.csv", data, "text/csv")})
    assert resp.status_code == 201, resp.text
    return resp.json()["created_items"][0]["ticket_id"]


def test_ticket_analyze_persists_multi_issue_fanout(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(llm, "analyze_ticket_text", _two_issue_analysis)
    ticket_id = _create_ticket(client, f"crash and double charge {uuid4().hex}")

    resp = client.post(f"/tickets/{ticket_id}/analyze")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created"] == 2
    cats = {i["category"] for i in body["issues"]}
    assert cats == {"bug", "incident"}
    critical = next(i for i in body["issues"] if i["category"] == "incident")
    assert critical["severity"] == "critical"
    assert critical["urgency_score"] == 0.9
    assert critical["themes"] == ["incident-theme"]


def test_ticket_analyze_unknown_id_returns_404(client: TestClient) -> None:
    resp = client.post(f"/tickets/{uuid4()}/analyze")
    assert resp.status_code == 404


def test_ticket_analyze_without_key_degrades_to_503(
    client: TestClient,
) -> None:
    llm.get_openai_client.cache_clear()
    ticket_id = _create_ticket(client, f"genuine issue text {uuid4().hex}")
    resp = client.post(f"/tickets/{ticket_id}/analyze")
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "ai_unavailable"
