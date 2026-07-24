"""User model."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.chat_session import ChatSession
    from app.models.ticket import Ticket


class User(Base, TimestampMixin):
    """A person who owns tickets and participates in chat sessions."""

    __tablename__ = "users"
    __table_args__ = (
        # A given identity from a provider maps to exactly one user. Nullable
        # columns (legacy/seed users) are excluded from the constraint by NULLs.
        UniqueConstraint("oauth_provider", "oauth_subject", name="users_oauth_identity"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    # StrEnum stored as its string value in a plain String column.
    role: Mapped[UserRole] = mapped_column(String(32), default=UserRole.MEMBER, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ---- Phase 5: OAuth/OIDC identity ----
    # Which provider authenticated this user ("google" | "apple") and the stable
    # subject id from that provider. Together they uniquely identify the account.
    # Nullable so pre-auth/seed rows remain valid.
    oauth_provider: Mapped[str | None] = mapped_column(String(32))
    oauth_subject: Mapped[str | None] = mapped_column(String(255), index=True)

    # ---- Phase 5: email + password identity ----
    # bcrypt hash; None for OAuth-only accounts (they never set a password).
    password_hash: Mapped[str | None] = mapped_column(String(255))

    # back_populates="owner": Ticket holds the foreign key to User; this side is
    # the reverse of that relationship. cascade="all, delete-orphan": deleting a
    # user also deletes all of their tickets.
    tickets: Mapped[list[Ticket]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    chat_sessions: Mapped[list[ChatSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<User id={self.id} email={self.email!r} role={self.role}>"
