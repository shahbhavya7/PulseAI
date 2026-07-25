"""chat cross-session memory: session_summaries (pgvector)

Revision ID: 0006_session_summaries
Revises: 0005_user_password_hash
Create Date: 2026-07-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0006_session_summaries"
down_revision: str | None = "0005_user_password_hash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.create_table(
        "session_summaries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("session_id", name="session_summaries_session_id_key"),
    )
    op.create_index("ix_session_summaries_user_id", "session_summaries", ["user_id"])
    op.create_index("ix_session_summaries_user", "session_summaries", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_session_summaries_user", table_name="session_summaries")
    op.drop_index("ix_session_summaries_user_id", table_name="session_summaries")
    op.drop_table("session_summaries")
