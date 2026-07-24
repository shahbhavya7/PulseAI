"""issue re-embed marker; weekly summary per (user, week)

Revision ID: 0003_embeddings_and_user_week
Revises: 0002_issue_ai_fields
Create Date: 2026-07-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_embeddings_and_user_week"
down_revision: str | None = "0002_issue_ai_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- issues: re-embed marker (the embedding column already exists) ---
    op.add_column(
        "issues",
        sa.Column("needs_reembed", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_index("ix_issues_needs_reembed", "issues", ["needs_reembed"])

    # --- weekly_summaries: move from unique(week) to per-(user, week) ---
    op.drop_index("ix_weekly_summaries_week", table_name="weekly_summaries")
    op.drop_constraint("weekly_summaries_week", "weekly_summaries", type_="unique")
    op.add_column("weekly_summaries", sa.Column("user_id", sa.Uuid(), nullable=False))
    op.create_foreign_key(
        "fk_weekly_summaries_user_id_users",
        "weekly_summaries",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_weekly_summaries_user_id", "weekly_summaries", ["user_id"])
    op.create_index("ix_weekly_summaries_week", "weekly_summaries", ["week"])
    op.create_unique_constraint(
        "weekly_summaries_user_week", "weekly_summaries", ["user_id", "week"]
    )


def downgrade() -> None:
    op.drop_constraint("weekly_summaries_user_week", "weekly_summaries", type_="unique")
    op.drop_index("ix_weekly_summaries_week", table_name="weekly_summaries")
    op.drop_index("ix_weekly_summaries_user_id", table_name="weekly_summaries")
    op.drop_constraint("fk_weekly_summaries_user_id_users", "weekly_summaries", type_="foreignkey")
    op.drop_column("weekly_summaries", "user_id")
    op.create_index("ix_weekly_summaries_week", "weekly_summaries", ["week"], unique=True)
    op.create_unique_constraint("weekly_summaries_week", "weekly_summaries", ["week"])

    op.drop_index("ix_issues_needs_reembed", table_name="issues")
    op.drop_column("issues", "needs_reembed")
