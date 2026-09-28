"""Add application-owned assistant tables.

Revision ID: dcc930ae8162
Revises: observability_outbox_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "dcc930ae8162"
down_revision: str | Sequence[str] | None = "observability_outbox_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_assistant_conversations_user_project",
        "assistant_conversations",
        ["user_id", "project_id", "updated_at"],
    )
    op.create_table(
        "assistant_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("references", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["assistant_conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_assistant_messages_conversation", "assistant_messages", ["conversation_id", "created_at"]
    )
    op.create_table(
        "assistant_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(32)),
        sa.Column("model", sa.String(100)),
        sa.Column("step_count", sa.Integer(), nullable=False),
        sa.Column("fallback_used", sa.Boolean(), nullable=False),
        sa.Column("proposed_action", sa.JSON()),
        sa.Column("result", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["assistant_conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_assistant_runs_conversation", "assistant_runs", ["conversation_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_assistant_runs_conversation", table_name="assistant_runs")
    op.drop_table("assistant_runs")
    op.drop_index("idx_assistant_messages_conversation", table_name="assistant_messages")
    op.drop_table("assistant_messages")
    op.drop_index("idx_assistant_conversations_user_project", table_name="assistant_conversations")
    op.drop_table("assistant_conversations")
