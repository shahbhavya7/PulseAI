"""Hybrid retrieval for chat: exact SQL facts + semantic pgvector examples.

For a user's question we gather two grounded, user-scoped context blocks:

* **Facts** — the same aggregates the dashboard shows (`compute_stats`): totals,
  category distribution, severity counts, sentiment trend, top themes. These are
  exact SQL numbers the model must not contradict.
* **Examples** — the issues most semantically similar to the question, found by
  embedding the question and ordering by pgvector cosine distance, always
  filtered to the acting user (and optional week/category). These let the model
  cite real, relevant tickets.

Everything is filtered by ``user_id`` at the SQL level, so retrieval can only
ever surface the caller's own data — the core guardrail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.enums import IssueCategory
from app.models.issue import Issue
from app.models.ticket import Ticket
from app.schemas.stats import StatsResponse
from app.services.llm import LLMError
from app.services.stats import compute_stats
from app.services.vector_store import VectorStore

logger = get_logger(__name__)

_EXAMPLE_MAX_CHARS = 240


@dataclass
class RetrievedIssue:
    """One issue example surfaced for grounding, with a stable citation id."""

    issue_id: UUID
    title: str
    category: str
    severity: str
    week: str
    sentiment_score: float
    urgency_score: float
    text: str


@dataclass
class ChatContext:
    """The grounded context for one question: exact facts + semantic examples."""

    stats: StatsResponse | None
    examples: list[RetrievedIssue] = field(default_factory=list)
    # True when we could run the semantic search (embeddings available).
    semantic_ok: bool = False


def _semantic_examples(
    db: Session,
    user_id: UUID,
    question: str,
    *,
    week: str | None,
    category: str | None,
    vector_store: VectorStore,
    k: int,
) -> list[RetrievedIssue]:
    """Nearest issues to the question by pgvector distance, user-scoped."""
    query_vec = vector_store.embed_one(question)  # LLMError propagates to caller
    stmt = (
        select(Issue)
        .join(Ticket, Issue.ticket_id == Ticket.id)
        .where(Ticket.owner_id == user_id)
        .where(Issue.embedding.is_not(None))
        .order_by(Issue.embedding.cosine_distance(query_vec))
        .limit(k)
    )
    if week is not None:
        stmt = stmt.where(Issue.week == week)
    if category is not None:
        stmt = stmt.where(Issue.category == IssueCategory(category))

    out: list[RetrievedIssue] = []
    for issue in db.scalars(stmt):
        text = (issue.description or issue.title or "")[:_EXAMPLE_MAX_CHARS]
        out.append(
            RetrievedIssue(
                issue_id=issue.id,
                title=issue.title,
                category=str(issue.category),
                severity=str(issue.severity),
                week=issue.week,
                sentiment_score=issue.sentiment_score,
                urgency_score=issue.urgency_score,
                text=text,
            )
        )
    return out


def retrieve_context(
    db: Session,
    user_id: UUID,
    question: str,
    *,
    week: str | None = None,
    category: str | None = None,
    vector_store: VectorStore | None = None,
) -> ChatContext:
    """Build the hybrid grounding context for ``question`` (user-scoped).

    SQL facts are always computed. Semantic examples are best-effort: if no
    vector store / API key / embeddings exist, we degrade to facts-only rather
    than fail the chat.
    """
    settings = get_settings()

    # Exact facts (pure SQL; never needs the model).
    stats: StatsResponse | None
    try:
        stats = compute_stats(db, user_id, week=week, vector_store=None)
    except Exception as exc:  # noqa: BLE001 — facts are best-effort context
        logger.warning("Stats retrieval failed; continuing without facts: %s", exc)
        stats = None

    examples: list[RetrievedIssue] = []
    semantic_ok = False
    if vector_store is not None:
        try:
            examples = _semantic_examples(
                db,
                user_id,
                question,
                week=week,
                category=category,
                vector_store=vector_store,
                k=settings.chat_retrieval_k,
            )
            semantic_ok = True
        except LLMError as exc:
            logger.info("Semantic retrieval unavailable; facts-only: %s", exc)

    return ChatContext(stats=stats, examples=examples, semantic_ok=semantic_ok)
