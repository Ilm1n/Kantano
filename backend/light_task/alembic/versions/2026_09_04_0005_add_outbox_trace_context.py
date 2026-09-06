"""add trace context to registration outbox

Revision ID: observability_outbox_0005
Revises: registration_password_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "observability_outbox_0005"
down_revision: str | Sequence[str] | None = "registration_password_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "outbox_events",
        sa.Column("trace_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("outbox_events", "trace_context")
