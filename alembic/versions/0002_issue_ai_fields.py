"""add AI-analysis columns to issues

Revision ID: 0002_issue_ai_fields
Revises: 0001_initial
Create Date: 2026-07-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_issue_ai_fields"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "issues",
        sa.Column("sentiment_score", sa.Float(), server_default="0", nullable=False),
    )
    op.add_column(
        "issues",
        sa.Column("urgency_score", sa.Float(), server_default="0", nullable=False),
    )
    op.add_column(
        "issues",
        sa.Column(
            "themes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "issues",
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Support "most urgent first" queries in later phases.
    op.create_index("ix_issues_urgency_score", "issues", ["urgency_score"])


def downgrade() -> None:
    op.drop_index("ix_issues_urgency_score", table_name="issues")
    op.drop_column("issues", "analyzed_at")
    op.drop_column("issues", "themes")
    op.drop_column("issues", "urgency_score")
    op.drop_column("issues", "sentiment_score")
