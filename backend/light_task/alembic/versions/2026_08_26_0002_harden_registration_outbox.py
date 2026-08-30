"""harden registration outbox

Revision ID: registration_harden_0002
Revises: email_verify_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "registration_harden_0002"
down_revision: str | Sequence[str] | None = "email_verify_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_pending_registrations_username",
        "pending_registrations",
        type_="unique",
    )
    op.create_index(
        "ix_pending_registrations_username",
        "pending_registrations",
        ["username"],
        unique=False,
    )
    op.add_column(
        "pending_registrations",
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "outbox_events",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("outbox_events", sa.Column("last_error", sa.String(length=500), nullable=True))
    op.create_index("ix_outbox_events_next_attempt_at", "outbox_events", ["next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_outbox_events_next_attempt_at", table_name="outbox_events")
    op.drop_column("outbox_events", "last_error")
    op.drop_column("outbox_events", "next_attempt_at")
    op.drop_column("pending_registrations", "email_sent_at")
    op.drop_index("ix_pending_registrations_username", table_name="pending_registrations")
    op.create_unique_constraint(
        "uq_pending_registrations_username",
        "pending_registrations",
        ["username"],
    )
