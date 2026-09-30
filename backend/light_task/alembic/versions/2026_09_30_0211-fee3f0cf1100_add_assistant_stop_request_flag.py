"""add assistant stop request flag

Revision ID: fee3f0cf1100
Revises: dbcf96c53b5a
Create Date: 2026-09-30 02:11:08.966276

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fee3f0cf1100"
down_revision: str | Sequence[str] | None = "dbcf96c53b5a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assistant_runs",
        sa.Column("stop_requested", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("assistant_runs", "stop_requested")
