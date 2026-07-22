"""Issue model — the atomic unit of work.

Each issue is one discrete, actionable item extracted from a ticket. It carries
the AI-triage metadata the rest of the system reasons about:

* ``confidence`` — model confidence in the extraction/classification [0, 1].
* ``needs_manual_review`` — set when confidence is low or a flag demands a human.
* ``flags`` — free-form list of machine/human annotations (e.g. ``["pii"]``).
* ``content_hash`` — stable hash of the canonical content for dedupe/idempotency.
* ``week`` — ISO week bucket (``"YYYY-Www"``) used by weekly summaries.
* ``embedding`` — optional pgvector embedding for semantic search/clustering.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import IssueCategory, IssueSeverity, IssueStatus

if TYPE_CHECKING:
    from app.models.ticket import Ticket

# Embedding dimensionality. Kept as a module constant so the migration and any
# embedding service agree on a single source of truth.
EMBEDDING_DIM = 1536


class Issue(Base, TimestampMixin):
    """A single actionable issue derived from a ticket."""

    __tablename__ = "issues"
    __table_args__ = (
        # A given piece of content appears at most once per ticket.
        UniqueConstraint("ticket_id", "content_hash", name="issues_ticket_content_hash"),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="confidence_range",
        ),
        Index("ix_issues_week_status", "week", "status"),
        Index("ix_issues_needs_manual_review", "needs_manual_review"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), index=True, nullable=False
    )

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    category: Mapped[IssueCategory] = mapped_column(
        String(32), default=IssueCategory.OTHER, nullable=False
    )
    severity: Mapped[IssueSeverity] = mapped_column(
        String(32), default=IssueSeverity.MEDIUM, nullable=False
    )
    status: Mapped[IssueStatus] = mapped_column(
        String(32), default=IssueStatus.OPEN, index=True, nullable=False
    )

    # ---- AI-triage metadata ----
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    needs_manual_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    flags: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    week: Mapped[str] = mapped_column(String(8), index=True, nullable=False)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))

    ticket: Mapped[Ticket] = relationship(back_populates="issues")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<Issue id={self.id} status={self.status} "
            f"severity={self.severity} confidence={self.confidence:.2f}>"
        )

    @property
    def metadata_summary(self) -> dict[str, Any]:
        """Compact dict of triage metadata, handy for logs and API responses."""
        return {
            "confidence": self.confidence,
            "needs_manual_review": self.needs_manual_review,
            "flags": self.flags,
            "week": self.week,
        }
