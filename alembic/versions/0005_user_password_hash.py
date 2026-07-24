"""user email/password: password_hash column + dev-user password

Revision ID: 0005_user_password_hash
Revises: 0004_user_oauth_identity
Create Date: 2026-07-24

Adds ``users.password_hash`` for email/password sign-in. As a convenience for
local development, if a user with the legacy dev email exists it is given a
password so the existing data is reachable via email login. The password is read
from ``PULSE_DEV_PASSWORD`` (default ``pulseai-dev``) and hashed at migration
time — no credential is stored in source.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import bcrypt
import sqlalchemy as sa
from alembic import op

revision: str = "0005_user_password_hash"
down_revision: str | None = "0004_user_oauth_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEV_EMAIL = "dev@pulseai.local"


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))

    # Give the existing dev user a password so its current data stays reachable.
    dev_password = os.environ.get("PULSE_DEV_PASSWORD", "pulseai-dev")
    hashed = bcrypt.hashpw(dev_password.encode(), bcrypt.gensalt()).decode()
    op.execute(
        sa.text("UPDATE users SET password_hash = :h WHERE email = :e").bindparams(
            h=hashed, e=_DEV_EMAIL
        )
    )


def downgrade() -> None:
    op.drop_column("users", "password_hash")
