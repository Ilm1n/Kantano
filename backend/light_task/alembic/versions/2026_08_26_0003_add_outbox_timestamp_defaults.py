"""add outbox timestamp defaults

Revision ID: registration_timestamps_0003
Revises: registration_harden_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "registration_timestamps_0003"
down_revision: str | Sequence[str] | None = "registration_harden_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table_name in ("pending_registrations", "outbox_events"):
        op.alter_column(
            table_name,
            "created_at",
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )
        op.alter_column(
            table_name,
            "updated_at",
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )


def downgrade() -> None:
    for table_name in ("pending_registrations", "outbox_events"):
        op.alter_column(table_name, "updated_at", server_default=None)
        op.alter_column(table_name, "created_at", server_default=None)
