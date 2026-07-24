"""SessionSummary model — the cross-session memory of a chat.

When a chat session ends (or goes idle), we distil it into a short note of
salient facts and stated preferences, embed that note, and store it here tagged
by ``user_id``. On a *new* session we retrieve the user's nearest prior summaries
by pgvector similarity and feed them in as context.

We deliberately embed the SUMMARY, never the raw messages: it keeps the memory
compact, avoids re-embedding chit-chat, and stores durable facts rather than
transcript noise (the full transcript lives in ``chat_messages``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.issue import EMBEDDING_DIM

if TYPE_CHECKING:
    from app.models.chat_session import ChatSession
    from app.models.user import User


class SessionSummary(Base, TimestampMixin):
    """A distilled, embedded memory of one chat session (one row per session)."""

    __tablename__ = "session_summaries"
    __table_args__ = (
        # Cross-session recall filters by user then orders by vector distance.
        Index("ix_session_summaries_user", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    # The salient-facts note (human-readable; also what we embed).
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))

    user: Mapped[User] = relationship()
    session: Mapped[ChatSession] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<SessionSummary user={self.user_id} session={self.session_id}>"
