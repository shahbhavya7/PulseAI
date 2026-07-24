"""Cross-session chat memory.

Two operations, both user-scoped:

* **write** (`summarize_session`) — when a session ends/idles, distil its
  transcript into a short note of salient facts + stated preferences, embed the
  note, and upsert one :class:`SessionSummary` row. We embed the *summary*, never
  the raw messages.
* **read** (`recall_summaries`) — on a new session, return the user's nearest
  prior session summaries (pgvector), so the assistant remembers earlier context.

Both degrade gracefully: if the model/embeddings are unavailable, writing stores
the note without an embedding (still readable as recent-fallback) and reading
returns an empty list rather than failing the chat.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from app.models.enums import ChatRole
from app.models.session_summary import SessionSummary
from app.services import llm
from app.services.llm import LLMError
from app.services.vector_store import VectorStore

logger = get_logger(__name__)

_TRANSCRIPT_MAX_TURNS = 40
_TURN_MAX_CHARS = 500


def _transcript(db: Session, session_id: UUID) -> str:
    """Render the session's user/assistant turns as plain text for summarising."""
    rows = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .where(ChatMessage.role.in_([ChatRole.USER, ChatRole.ASSISTANT]))
        .order_by(ChatMessage.created_at)
        .limit(_TRANSCRIPT_MAX_TURNS)
    ).all()
    lines = [f"{m.role}: {m.content[:_TURN_MAX_CHARS]}" for m in rows]
    return "\n".join(lines)


def summarize_session(
    db: Session,
    session: ChatSession,
    *,
    vector_store: VectorStore | None = None,
    summarizer: object | None = None,
) -> SessionSummary | None:
    """Distil, embed, and upsert the memory for ``session``.

    Returns the stored row, or ``None`` when the session has no substance to
    remember (no user/assistant turns). Never raises on model/embed failure.
    """
    transcript = _transcript(db, session.id)
    if not transcript.strip():
        return None

    summarize = summarizer or llm.summarize_chat_session
    try:
        content = summarize(transcript)  # type: ignore[operator]
    except LLMError as exc:
        logger.info("Session summary generation skipped (LLM unavailable): %s", exc)
        return None

    embedding: list[float] | None = None
    store = vector_store
    if store is not None:
        try:
            embedding = store.embed_one(content)
        except LLMError as exc:
            logger.info("Session summary embed skipped: %s", exc)

    # Upsert one row per session.
    row = db.scalar(select(SessionSummary).where(SessionSummary.session_id == session.id))
    if row is None:
        row = SessionSummary(user_id=session.user_id, session_id=session.id, content=content)
        db.add(row)
    else:
        row.content = content
    row.embedding = embedding
    db.commit()
    db.refresh(row)
    logger.info(
        "Stored session memory for session=%s (embedded=%s)",
        session.id,
        embedding is not None,
    )
    return row


def recall_summaries(
    db: Session,
    user_id: UUID,
    query: str,
    *,
    exclude_session_id: UUID | None = None,
    vector_store: VectorStore | None = None,
) -> list[str]:
    """Return the user's most relevant prior session-summary notes.

    With a vector store + embeddings, orders by pgvector similarity to ``query``;
    otherwise falls back to the most recent summaries. Always user-scoped.
    """
    settings = get_settings()
    k = settings.chat_memory_k

    base = select(SessionSummary).where(SessionSummary.user_id == user_id)
    if exclude_session_id is not None:
        base = base.where(SessionSummary.session_id != exclude_session_id)

    if vector_store is not None:
        try:
            query_vec = vector_store.embed_one(query)
        except LLMError:
            query_vec = None
        if query_vec is not None:
            stmt = (
                base.where(SessionSummary.embedding.is_not(None))
                .order_by(SessionSummary.embedding.cosine_distance(query_vec))
                .limit(k)
            )
            notes = [s.content for s in db.scalars(stmt)]
            if notes:
                return notes

    # Fallback: most recent summaries.
    stmt = base.order_by(SessionSummary.created_at.desc()).limit(k)
    return [s.content for s in db.scalars(stmt)]
