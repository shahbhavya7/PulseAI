"""user OAuth identity (provider + subject)

Revision ID: 0004_user_oauth_identity
Revises: 0003_embeddings_and_user_week
Create Date: 2026-07-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_user_oauth_identity"
down_revision: str | None = "0003_embeddings_and_user_week"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("oauth_provider", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("oauth_subject", sa.String(length=255), nullable=True))
    op.create_index("ix_users_oauth_subject", "users", ["oauth_subject"])
    # (provider, subject) is unique; NULLs (legacy/seed rows) are exempt in PG.
    op.create_unique_constraint(
        "users_oauth_identity", "users", ["oauth_provider", "oauth_subject"]
    )


def downgrade() -> None:
    op.drop_constraint("users_oauth_identity", "users", type_="unique")
    op.drop_index("ix_users_oauth_subject", table_name="users")
    op.drop_column("users", "oauth_subject")
    op.drop_column("users", "oauth_provider")
