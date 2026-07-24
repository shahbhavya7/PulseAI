"""WeeklySummary model — a generated digest of a week's issues."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import SummaryStatus

if TYPE_CHECKING:
    from app.models.user import User


class WeeklySummary(Base, TimestampMixin):
    """A rollup of one user's issue activity for one ISO week (``"YYYY-Www"``).

    Exactly one row per ``(user_id, week)`` — regenerating a week's summary
    updates that single row.
    """

    __tablename__ = "weekly_summaries"
    __table_args__ = (UniqueConstraint("user_id", "week", name="weekly_summaries_user_week"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    week: Mapped[str] = mapped_column(String(8), index=True, nullable=False)

    status: Mapped[SummaryStatus] = mapped_column(
        String(32), default=SummaryStatus.PENDING, nullable=False
    )
    content: Mapped[str | None] = mapped_column(Text)  # VP-actionable narrative
    issue_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Computed metrics + ranked themes (see services/summaries.py).
    stats: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    user: Mapped[User] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<WeeklySummary user={self.user_id} week={self.week} status={self.status}>"
