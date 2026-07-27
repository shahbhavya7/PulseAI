"""Tests for Phase 6 chat: hybrid retrieval, cross-session memory, isolation, and
the streaming session flow. All model/embedding calls are faked — no OpenAI key.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_sessionmaker
from app.models.enums import ChatRole, ChatSessionStatus
from app.models.user import User
from app.schemas.ai import (
    Classification,
    IssueAnalysis,
    SentimentUrgency,
    Themes,
    TicketAnalysis,
)
from app.services import chat as chat_svc
from app.services import chat_memory, llm, pipeline

pytestmark = pytest.mark.usefixtures("require_db")


# ---- fakes -----------------------------------------------------------------


class _FakeStore:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.02] * 1536 for _ in texts]

    def embed_one(self, text: str) -> list[float]:
        return [0.02] * 1536


def _two_issues(_text: str) -> TicketAnalysis:
    def mk(summary: str, category: str, urgency: str, theme: str) -> IssueAnalysis:
        return IssueAnalysis(
            is_valid_ticket=True,
            summary=summary,
            classification=Classification(category=category, confidence=0.9),  # type: ignore[arg-type]
            sentiment_urgency=SentimentUrgency(
                sentiment_score=-0.6,
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


def _new_user(name: str = "Chat Tester") -> str:
    with get_sessionmaker()() as db:
        user = User(email=f"{uuid4().hex}@test.local", full_name=name)
        db.add(user)
        db.commit()
        return str(user.id)


def _seed_analyzed_ticket(client: TestClient, text: str) -> None:
    data = (f"text\n{text}\n").encode()
    up = client.post("/uploads", files={"file": ("t.csv", data, "text/csv")})
    assert up.status_code == 201, up.text
    tid = up.json()["created_items"][0]["ticket_id"]
    an = client.post(f"/tickets/{tid}/analyze")
    assert an.status_code == 200, an.text


# ---- hybrid retrieval ------------------------------------------------------


def test_retrieval_returns_facts_and_examples(
    client: TestClient, as_user: Callable[[str], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from uuid import UUID

    from app.services.chat_retrieval import retrieve_context

    monkeypatch.setattr(llm, "analyze_ticket_text", _two_issues)
    monkeypatch.setattr(pipeline, "get_vector_store", _FakeStore)
    uid = as_user(_new_user())
    _seed_analyzed_ticket(client, f"crash and double charge {uuid4().hex}")

    with get_sessionmaker()() as db:
        ctx = retrieve_context(db, UUID(uid), "why is the app crashing?", vector_store=_FakeStore())
    assert ctx.stats is not None
    assert ctx.stats.total_issues == 2
    assert ctx.semantic_ok
    assert len(ctx.examples) >= 1  # nearest issues surfaced


# ---- cross-session memory --------------------------------------------------


def test_memory_summarize_then_recall(
    client: TestClient, as_user: Callable[[str], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from uuid import UUID

    from app.models.chat_session import ChatSession

    # Fake the session summariser (plain text) + embeddings.
    monkeypatch.setattr(
        llm, "summarize_chat_session", lambda _t: "User cares about photo-upload crashes."
    )
    uid = as_user(_new_user())

    with get_sessionmaker()() as db:
        session = ChatSession(user_id=UUID(uid), status=ChatSessionStatus.ACTIVE)
        db.add(session)
        db.commit()
        db.refresh(session)
        db.add_all(
            [
                _msg(session.id, ChatRole.USER, "why does photo upload crash?"),
                _msg(session.id, ChatRole.ASSISTANT, "One ticket reports a photo-upload crash."),
            ]
        )
        db.commit()

        row = chat_memory.summarize_session(db, session, vector_store=_FakeStore())
        assert row is not None
        assert "photo-upload" in row.content
        assert row.embedding is not None

        # A NEW session recalls it (exclude the source session).
        recalled = chat_memory.recall_summaries(
            db, UUID(uid), "photo upload", vector_store=_FakeStore()
        )
        assert any("photo-upload" in note for note in recalled)


def _msg(session_id: object, role: ChatRole, content: str) -> object:
    from app.models.chat_message import ChatMessage

    return ChatMessage(session_id=session_id, role=role, content=content)


# ---- isolation -------------------------------------------------------------


def test_memory_is_user_scoped(as_user: Callable[[str], str]) -> None:
    from uuid import UUID

    from app.models.chat_session import ChatSession

    a = _new_user("A")
    b = _new_user("B")
    with get_sessionmaker()() as db:
        sess = ChatSession(user_id=UUID(a), status=ChatSessionStatus.ACTIVE)
        db.add(sess)
        db.commit()
        db.refresh(sess)
        db.add(_msg(sess.id, ChatRole.USER, "remember: I like dark mode"))
        db.commit()
        chat_memory.summarize_session(
            db, sess, vector_store=_FakeStore(), summarizer=lambda _t: "A likes dark mode."
        )

        # User B recalls nothing from A.
        b_recall = chat_memory.recall_summaries(db, UUID(b), "dark mode", vector_store=_FakeStore())
        assert b_recall == []


# ---- session flow (API + SSE) ----------------------------------------------


def test_chat_session_flow_streams_and_persists(
    client: TestClient, as_user: Callable[[str], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(llm, "analyze_ticket_text", _two_issues)
    monkeypatch.setattr(pipeline, "get_vector_store", _FakeStore)
    monkeypatch.setattr(chat_svc, "get_vector_store", _FakeStore)
    # Grounded answer: stream a couple of tokens (no real model).
    monkeypatch.setattr(
        llm, "stream_chat_answer", lambda _ctx, _hist: iter(["You have ", "2 issues."])
    )
    as_user(_new_user())
    _seed_analyzed_ticket(client, f"crash and double charge {uuid4().hex}")

    # Create a session, ask a question, read the SSE stream.
    sess = client.post("/chat/sessions", json={"title": "T"})
    assert sess.status_code == 201
    sid = sess.json()["id"]

    resp = client.post(f"/chat/sessions/{sid}/messages", json={"message": "how many issues?"})
    assert resp.status_code == 200
    tokens = _sse_tokens(resp.text)
    assert "".join(tokens) == "You have 2 issues."

    # The transcript persisted both turns.
    detail = client.get(f"/chat/sessions/{sid}").json()
    roles = [m["role"] for m in detail["messages"]]
    assert roles == ["user", "assistant"]
    assert detail["messages"][1]["content"] == "You have 2 issues."


def test_chat_degrades_when_llm_unavailable(
    client: TestClient, as_user: Callable[[str], str]
) -> None:
    # No OpenAI key (conftest clears it) and no monkeypatch → the grounded call
    # fails; the stream must still return a graceful message, not 500.
    as_user(_new_user())
    sess = client.post("/chat/sessions", json={}).json()
    resp = client.post(f"/chat/sessions/{sess['id']}/messages", json={"message": "hi"})
    assert resp.status_code == 200
    text = "".join(_sse_tokens(resp.text))
    assert "unavailable" in text.lower()


def test_chat_session_requires_auth(client: TestClient) -> None:
    resp = client.get("/chat/sessions")
    assert resp.status_code == 401


def test_chat_other_users_session_404(client: TestClient, as_user: Callable[[str], str]) -> None:
    # Session created by A …
    as_user(_new_user("A"))
    sid = client.post("/chat/sessions", json={}).json()["id"]
    # … is invisible to B.
    as_user(_new_user("B"))
    assert client.get(f"/chat/sessions/{sid}").status_code == 404


def test_sessions_are_capped_and_oldest_are_pruned(
    client: TestClient, as_user: Callable[[str], str]
) -> None:
    """Creating sessions past the cap deletes the oldest, keeping the newest N."""
    from app.core.config import get_settings

    limit = get_settings().chat_session_limit
    as_user(_new_user("Pruner"))

    created = [
        client.post("/chat/sessions", json={"title": f"s{i}"}).json()["id"]
        for i in range(limit + 3)
    ]

    listed = client.get("/chat/sessions").json()
    assert len(listed) == limit, f"expected {limit} sessions, got {len(listed)}"

    # The survivors are the most recent ones; the earliest are gone for good.
    surviving = {s["id"] for s in listed}
    assert surviving == set(created[-limit:])
    for gone in created[:-limit]:
        assert client.get(f"/chat/sessions/{gone}").status_code == 404


def test_pruning_is_per_user(client: TestClient, as_user: Callable[[str], str]) -> None:
    """One user hitting the cap must never delete another user's conversations."""
    from app.core.config import get_settings

    limit = get_settings().chat_session_limit

    keeper = _new_user("Keeper")
    as_user(keeper)
    keeper_sid = client.post("/chat/sessions", json={"title": "keep me"}).json()["id"]

    # A second user churns well past the cap.
    as_user(_new_user("Churner"))
    for i in range(limit + 3):
        client.post("/chat/sessions", json={"title": f"c{i}"})

    # The first user's session survives untouched.
    as_user(keeper)
    assert client.get(f"/chat/sessions/{keeper_sid}").status_code == 200
    assert [s["id"] for s in client.get("/chat/sessions").json()] == [keeper_sid]


def _sse_tokens(body: str) -> list[str]:
    tokens: list[str] = []
    for line in body.splitlines():
        if line.startswith("data:"):
            raw = line[5:].strip()
            if not raw or raw == "{}":
                continue
            payload = json.loads(raw)
            if "token" in payload:
                tokens.append(payload["token"])
    return tokens
