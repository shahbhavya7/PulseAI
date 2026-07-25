"""Integration tests for POST /uploads (require a live Postgres).

Content is made unique per run with ``uuid4`` so persisted rows from earlier
runs don't dedup these away.
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


def _fake_bug(_text: str) -> TicketAnalysis:
    return TicketAnalysis(
        issues=[
            IssueAnalysis(
                summary="Login page throws an error on submit",
                classification=Classification(category="bug", confidence=0.92),  # type: ignore[arg-type]
                sentiment_urgency=SentimentUrgency(
                    sentiment_score=-0.4,
                    sentiment_label="negative",  # type: ignore[arg-type]
                    urgency_score=0.7,
                    urgency_label="high",  # type: ignore[arg-type]
                ),
                themes=Themes(labels=["login error"]),
            )
        ]
    )


class _FakeStore:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.01] * 1536 for _ in texts]

    def embed_one(self, text: str) -> list[float]:
        return [0.01] * 1536


def _csv(*rows: str, header: str = "text") -> bytes:
    return (header + "\n" + "\n".join(rows) + "\n").encode()


@pytest.fixture(autouse=True)
def _auth(require_db: None, as_user: Callable[[str], str]) -> None:
    """Authenticate every upload test as a fresh, isolated user."""
    with get_sessionmaker()() as db:
        user = User(email=f"{uuid4().hex}@test.local", full_name="Upload Tester")
        db.add(user)
        db.commit()
        as_user(str(user.id))


def test_upload_csv_creates_tickets(client: TestClient) -> None:
    marker = uuid4().hex
    data = _csv(f"Login page throws an error {marker}", f"Checkout is very slow {marker}")
    resp = client.post("/uploads", files={"file": ("issues.csv", data, "text/csv")})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["parser"] == "csv"
    assert body["counts"]["created"] == 2
    assert len(body["created_items"]) == 2
    assert body["created_items"][0]["ticket_id"] and body["created_items"][0]["issue_id"]


def test_upload_counts_blanks_and_duplicates(client: TestClient) -> None:
    marker = uuid4().hex
    data = _csv(
        f"Unique complaint {marker}",
        "",  # blank row
        f"unique   complaint   {marker}",  # duplicate after normalisation
    )
    resp = client.post("/uploads", files={"file": ("mix.csv", data, "text/csv")})
    assert resp.status_code == 201, resp.text
    counts = resp.json()["counts"]
    assert counts["created"] == 1 and counts["blanks"] == 1 and counts["duplicates"] == 1


def test_upload_redacts_pii_before_storage(client: TestClient) -> None:
    marker = uuid4().hex
    data = _csv(f"Email me at user@example.com about {marker}")
    resp = client.post("/uploads", files={"file": ("pii.csv", data, "text/csv")})
    assert resp.status_code == 201, resp.text
    assert "pii_redacted" in resp.json()["created_items"][0]["flags"]


def test_upload_missing_text_column_returns_422(client: TestClient) -> None:
    resp = client.post(
        "/uploads",
        files={"file": ("bad.csv", b"id,priority\n1,high\n2,low\n", "text/csv")},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "missing_text_column"


def test_upload_dedup_across_two_uploads(client: TestClient) -> None:
    marker = uuid4().hex
    data = _csv(f"Repeated across uploads {marker}")
    first = client.post("/uploads", files={"file": ("a.csv", data, "text/csv")})
    assert first.json()["counts"]["created"] == 1
    second = client.post("/uploads", files={"file": ("b.csv", data, "text/csv")})
    assert second.status_code == 201
    counts = second.json()["counts"]
    assert counts["created"] == 0 and counts["duplicates"] == 1


def test_upload_text_file_boundary_split(client: TestClient) -> None:
    marker = uuid4().hex
    blob = (
        f"From: alice@example.com\nOrder {marker} never arrived.\n"
        f"From: bob@example.com\nWrong item {marker} shipped."
    ).encode()
    resp = client.post("/uploads", files={"file": ("thread.txt", blob, "text/plain")})
    assert resp.status_code == 201, resp.text
    assert resp.json()["counts"]["created"] == 2


def test_upload_auto_classifies_when_model_available(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the model available, uploaded tickets are classified in the same request."""
    monkeypatch.setattr(llm, "analyze_ticket_text", _fake_bug)
    monkeypatch.setattr(pipeline, "get_vector_store", _FakeStore)
    marker = uuid4().hex
    data = _csv(f"Login page throws an error {marker}")
    resp = client.post("/uploads", files={"file": ("issues.csv", data, "text/csv")})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["counts"]["created"] == 1
    assert body["analyzed"] is True
    assert body["analyzed_count"] == 1
    # The persisted issue is the classified fan-out, not the OTHER placeholder.
    tickets = client.get("/tickets").json()["tickets"]
    assert tickets[0]["issues"][0]["category"] == "bug"


def test_upload_degrades_when_model_unavailable(client: TestClient) -> None:
    """No key (the default test env) → upload still succeeds with a placeholder issue."""
    marker = uuid4().hex
    data = _csv(f"Something is broken here {marker}")
    resp = client.post("/uploads", files={"file": ("issues.csv", data, "text/csv")})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["counts"]["created"] == 1
    assert body["analyzed"] is False
    assert body["analyzed_count"] == 0
    # The ticket is stored and still browsable (unclassified placeholder).
    assert client.get("/tickets").json()["total"] == 1


def test_paste_text_creates_and_classifies_ticket(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(llm, "analyze_ticket_text", _fake_bug)
    monkeypatch.setattr(pipeline, "get_vector_store", _FakeStore)
    marker = uuid4().hex
    resp = client.post(
        "/uploads/text",
        json={"text": f"The login page throws an error {marker}", "title": "Login bug"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["parser"] == "text"
    assert body["counts"]["created"] == 1
    assert body["analyzed_count"] == 1
    assert "Login bug" in body["filename"]
    tickets = client.get("/tickets").json()["tickets"]
    assert tickets[0]["issues"][0]["category"] == "bug"


def test_paste_text_rejects_empty(client: TestClient) -> None:
    resp = client.post("/uploads/text", json={"text": "   "})
    # Whitespace-only cleans to nothing → 400 empty-file error (not a crash).
    assert resp.status_code in (400, 422)


def test_upload_requires_auth(client: TestClient) -> None:
    # Drop the autouse auth override → no session → 401 (real auth, no stub).
    from app.api.deps import get_current_user
    from app.main import app

    app.dependency_overrides.pop(get_current_user, None)
    resp = client.post(
        "/uploads",
        files={"file": ("x.csv", _csv("anything"), "text/csv")},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "not_authenticated"
