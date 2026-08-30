"""add email verification registration outbox

Revision ID: email_verify_0001
Revises: bcea414f0c52
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "email_verify_0001"
down_revision: str | Sequence[str] | None = "bcea414f0c52"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE users SET email_verified_at = CURRENT_TIMESTAMP")
    op.create_table(
        "pending_registrations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("username", sa.String(50), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_pending_registrations_expires_at", "pending_registrations", ["expires_at"])
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_outbox_events_event_type", "outbox_events", ["event_type"])


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_table("pending_registrations")
    op.drop_column("users", "email_verified_at")
