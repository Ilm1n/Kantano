"""add assistant checkpoint cleanup queue

Revision ID: dbcf96c53b5a
Revises: dcc930ae8162
Create Date: 2026-09-30 00:19:50.378124

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dbcf96c53b5a"
down_revision: str | Sequence[str] | None = "dcc930ae8162"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assistant_checkpoint_cleanup",
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("thread_id"),
    )


def downgrade() -> None:
    op.drop_table("assistant_checkpoint_cleanup")
