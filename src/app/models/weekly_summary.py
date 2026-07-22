"""WeeklySummary model — a generated digest of a week's issues."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import SummaryStatus


class WeeklySummary(Base, TimestampMixin):
    """A rollup of issue activity for one ISO week (``"YYYY-Www"``)."""

    __tablename__ = "weekly_summaries"
    __table_args__ = (UniqueConstraint("week", name="weekly_summaries_week"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    week: Mapped[str] = mapped_column(String(8), unique=True, index=True, nullable=False)

    status: Mapped[SummaryStatus] = mapped_column(
        String(32), default=SummaryStatus.PENDING, nullable=False
    )
    content: Mapped[str | None] = mapped_column(Text)
    issue_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Arbitrary computed stats (per-category counts, top severities, etc.).
    stats: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<WeeklySummary week={self.week} status={self.status}>"
