"""Ticket model — a container that decomposes into many issues."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import TicketPriority, TicketSource, TicketStatus

if TYPE_CHECKING:
    from app.models.issue import Issue
    from app.models.user import User


class Ticket(Base, TimestampMixin):
    """An inbound request. One ticket fans out into many :class:`Issue` rows."""

    __tablename__ = "tickets"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)

    source: Mapped[TicketSource] = mapped_column(
        String(32), default=TicketSource.MANUAL, nullable=False
    )
    status: Mapped[TicketStatus] = mapped_column(
        String(32), default=TicketStatus.OPEN, index=True, nullable=False
    )
    priority: Mapped[TicketPriority] = mapped_column(
        String(32), default=TicketPriority.MEDIUM, nullable=False
    )
    # Provider-native identifier (e.g. Slack ts, email Message-ID) for dedupe.
    external_id: Mapped[str | None] = mapped_column(String(255), index=True)

    owner: Mapped[User] = relationship(back_populates="tickets")
    issues: Mapped[list[Issue]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="Issue.created_at",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Ticket id={self.id} status={self.status} title={self.title!r}>"
