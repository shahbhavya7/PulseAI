"""Chat orchestration — ties transcript, hybrid retrieval, and memory together.

Postgres (``chat_sessions`` / ``chat_messages``) is the transcript source of
truth. A turn:

1. persists the user's message,
2. retrieves grounding — exact SQL facts + semantic issue examples
   (`chat_retrieval`) plus the user's prior session summaries (`chat_memory`),
3. streams a grounded answer from the model,
4. persists the assistant's message.

Session end / idle sweep distils sessions into embedded memory
(`chat_memory.summarize_session`). Everything is scoped to the acting user.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from app.models.enums import ChatRole, ChatSessionStatus
from app.models.user import User
from app.schemas.analytics import AnalyticsTable
from app.services import chat_analytics, chat_memory, llm
from app.services.chat_retrieval import ChatContext, retrieve_context
from app.services.llm import LLMError
from app.services.vector_store import VectorStore, get_vector_store

logger = get_logger(__name__)


class ChatError(Exception):
    """Chat could not be served (bad session, etc.)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Session + message persistence (user-scoped)
# ---------------------------------------------------------------------------


def create_session(db: Session, user: User, *, title: str | None = None) -> ChatSession:
    session = ChatSession(user_id=user.id, title=title, status=ChatSessionStatus.ACTIVE)
    db.add(session)
    db.commit()
    db.refresh(session)
    # Keep the sidebar short: drop the user's oldest conversations past the cap.
    prune_sessions(db, user)
    return session


def prune_sessions(db: Session, user: User) -> int:
    """Delete the user's oldest sessions beyond ``chat_session_limit``.

    Keeps the most recently updated N conversations so the history list stays
    readable. Deleting a session cascades to its messages AND its
    :class:`SessionSummary`, so a pruned conversation is also forgotten by
    cross-session memory. That is intentional: memory the user can no longer
    see in the sidebar should not keep influencing answers.

    Returns the number of sessions deleted.
    """
    limit = get_settings().chat_session_limit
    stale = list(
        db.scalars(
            select(ChatSession)
            .where(ChatSession.user_id == user.id)
            .order_by(ChatSession.updated_at.desc())
            .offset(limit)
        )
    )
    if not stale:
        return 0
    for session in stale:
        db.delete(session)
    db.commit()
    logger.info("Pruned %d old chat session(s) for user=%s", len(stale), user.id)
    return len(stale)


def get_session(db: Session, user: User, session_id: UUID) -> ChatSession:
    session = db.get(ChatSession, session_id)
    if session is None or session.user_id != user.id:
        raise ChatError("session_not_found", "No such chat session.")
    return session


def list_sessions(db: Session, user: User) -> list[ChatSession]:
    return list(
        db.scalars(
            select(ChatSession)
            .where(ChatSession.user_id == user.id)
            .order_by(ChatSession.updated_at.desc())
        )
    )


def list_messages(db: Session, session: ChatSession) -> list[ChatMessage]:
    return list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at)
        )
    )


def _add_message(db: Session, session: ChatSession, role: ChatRole, content: str) -> ChatMessage:
    msg = ChatMessage(session_id=session.id, role=role, content=content)
    db.add(msg)
    # Touch the session so idle detection + ordering stay current.
    session.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(msg)
    return msg


# ---------------------------------------------------------------------------
# Grounding context
# ---------------------------------------------------------------------------


def _format_context(
    ctx: ChatContext,
    memory: list[str],
    analytics: str | None = None,
) -> str:
    """Render facts + examples + memory + live query results into <context>."""
    parts: list[str] = []

    # Live query results go FIRST: when present they answer the question more
    # precisely than the standing metrics, and the model should prefer them.
    if analytics:
        parts.append(analytics)

    if ctx.stats is not None:
        s = ctx.stats
        cats = ", ".join(f"{k}: {v}" for k, v in s.category_distribution.items()) or "none"
        sev = ", ".join(f"{k}: {v}" for k, v in s.urgency_counts.items()) or "none"
        themes = ", ".join(f"{t.theme} ({t.count})" for t in s.top_themes[:8]) or "none"
        trend = (
            "; ".join(
                f"{p.week}: sentiment {p.avg_sentiment:.2f}, "
                f"urgency {p.avg_urgency:.2f}, {p.issue_count} issues"
                for p in s.sentiment_over_time[-6:]
            )
            or "none"
        )
        parts.append(
            "METRICS (exact, from the user's data):\n"
            f"- total issues: {s.total_issues}\n"
            f"- by category: {cats}\n"
            f"- by severity: {sev}\n"
            f"- top themes: {themes}\n"
            f"- sentiment/urgency by week: {trend}"
        )

    if ctx.examples:
        lines = [
            f"[{i + 1}] ({e.category}/{e.severity}, {e.week}) {e.text}"
            for i, e in enumerate(ctx.examples)
        ]
        parts.append("RELEVANT ISSUE EXAMPLES:\n" + "\n".join(lines))
    elif ctx.semantic_ok:
        parts.append("RELEVANT ISSUE EXAMPLES: none matched.")

    if memory:
        parts.append(
            "NOTES FROM THE USER'S EARLIER SESSIONS:\n" + "\n".join(f"- {m}" for m in memory)
        )

    body = "\n\n".join(parts) if parts else "No data is available for this user yet."
    return f"<context>\n{body}\n</context>"


def _history(db: Session, session: ChatSession) -> list[dict[str, str]]:
    """Recent user/assistant turns as chat messages (window-limited)."""
    window = get_settings().chat_history_window
    rows = list_messages(db, session)
    turns = [m for m in rows if m.role in (ChatRole.USER, ChatRole.ASSISTANT)]
    return [{"role": str(m.role), "content": m.content} for m in turns[-window:]]


# ---------------------------------------------------------------------------
# A turn (streaming)
# ---------------------------------------------------------------------------


@dataclass
class TurnResult:
    """A streaming turn: the token iterator plus any analytics table it used.

    The table is resolved before streaming begins (the query runs during
    retrieval), so the route can emit it as an SSE frame ahead of the tokens.
    """

    tokens: Iterator[str]
    table: AnalyticsTable | None = None
    explanation: str = ""


def stream_turn(
    db: Session,
    user: User,
    session: ChatSession,
    question: str,
    *,
    week: str | None = None,
    category: str | None = None,
    vector_store: VectorStore | None = None,
) -> TurnResult:
    """Persist the question, retrieve grounding, and stream the grounded answer.

    Returns a :class:`TurnResult` whose ``tokens`` iterator yields the answer.
    The complete assistant message is persisted after the stream finishes. On
    LLM failure the iterator yields a graceful fallback sentence and persists
    that (never raises to the SSE layer).
    """
    store = vector_store
    if store is None:
        try:
            store = get_vector_store()
        except Exception:  # noqa: BLE001 — embeddings optional; degrade to facts-only
            store = None

    _add_message(db, session, ChatRole.USER, question)

    # Retrieval (facts always; examples + memory best-effort).
    ctx = retrieve_context(db, user.id, question, week=week, category=category, vector_store=store)
    memory = chat_memory.recall_summaries(
        db, user.id, question, exclude_session_id=session.id, vector_store=store
    )

    # Natural-language analytics: let the model write a read-only query when the
    # question needs a real aggregation (period comparisons, filtered counts)
    # that the standing metrics cannot answer. Never raises; on any failure the
    # answer just falls back to the metrics above.
    analytics = chat_analytics.run_analytics(db, user.id, question)
    if analytics.error:
        logger.info("Analytics unavailable for this turn: %s", analytics.error)

    system_context = _format_context(ctx, memory, chat_analytics.format_for_prompt(analytics))
    history = _history(db, session)

    collected: list[str] = []

    def _generate() -> Iterator[str]:
        try:
            for token in llm.stream_chat_answer(system_context, history):
                collected.append(token)
                yield token
            # Rare: a stream that completes with zero tokens. Retry once
            # non-streaming so the user still gets an answer.
            if not "".join(collected).strip():
                retry = llm.answer_chat(system_context, history)
                if retry.strip():
                    collected.append(retry)
                    yield retry
            # Still empty after the retry → give a helpful sentence rather than a
            # bare "(no answer)" placeholder in the transcript.
            if not "".join(collected).strip():
                empty = (
                    "I couldn't put together an answer for that one. Try rephrasing, "
                    "or ask me about your ticket categories, urgency, or top themes."
                )
                collected.append(empty)
                yield empty
        except LLMError as exc:
            logger.info("Chat answer degraded: %s", exc)
            fallback = (
                "The AI assistant is unavailable right now, so I can't answer that "
                "yet. Your data is safe — please try again shortly."
            )
            collected.append(fallback)
            yield fallback
        finally:
            answer = "".join(collected).strip() or "(no answer)"
            _add_message(db, session, ChatRole.ASSISTANT, answer)

    return TurnResult(
        tokens=_generate(),
        table=analytics.as_table(),
        explanation=analytics.explanation,
    )


# ---------------------------------------------------------------------------
# End + idle sweep (memory writing)
# ---------------------------------------------------------------------------


def end_session(
    db: Session,
    user: User,
    session: ChatSession,
    *,
    vector_store: VectorStore | None = None,
) -> None:
    """Archive a session and write its memory summary."""
    store = vector_store
    if store is None:
        try:
            store = get_vector_store()
        except Exception:  # noqa: BLE001
            store = None
    chat_memory.summarize_session(db, session, vector_store=store)
    session.status = ChatSessionStatus.ARCHIVED
    db.commit()


def sweep_idle_sessions(
    db: Session,
    user: User,
    *,
    now: datetime | None = None,
    vector_store: VectorStore | None = None,
) -> int:
    """Summarise + archive the user's ACTIVE sessions idle past the threshold.

    Returns how many were swept. Safe to call repeatedly (idempotent per run).
    """
    settings = get_settings()
    cutoff = (now or datetime.now(UTC)) - timedelta(minutes=settings.chat_idle_minutes)
    stale = list(
        db.scalars(
            select(ChatSession)
            .where(ChatSession.user_id == user.id)
            .where(ChatSession.status == ChatSessionStatus.ACTIVE)
            .where(ChatSession.updated_at < cutoff)
        )
    )
    for session in stale:
        end_session(db, user, session, vector_store=vector_store)
    return len(stale)
