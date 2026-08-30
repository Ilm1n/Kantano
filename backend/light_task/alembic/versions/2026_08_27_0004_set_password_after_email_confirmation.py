"""set password after email confirmation

Revision ID: registration_password_0004
Revises: registration_timestamps_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "registration_password_0004"
down_revision: str | Sequence[str] | None = "registration_timestamps_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("pending_registrations", "password_hash")


def downgrade() -> None:
    # Existing pending registrations cannot be restored safely without knowing their passwords.
    op.add_column(
        "pending_registrations",
        sa.Column("password_hash", sa.String(length=255), nullable=True),
    )
