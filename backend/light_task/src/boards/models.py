from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.boards.constants import TaskPriority
from src.db.base import Base
from src.db.mixins import TimestampMixin
from src.tags.models import Tag, task_tags

if TYPE_CHECKING:
    from src.projects.models import Project
    from src.users.models import User


class BoardColumn(Base, TimestampMixin):
    __tablename__ = "board_columns"
    __table_args__ = (
        CheckConstraint("length(name) > 0", name="check_column_name_length"),
        Index("idx_columns_project_pos", "project_id", "position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    position: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tasks_limit: Mapped[int | None] = mapped_column(nullable=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))

    project: Mapped["Project"] = relationship("Project", back_populates="board_columns")
    tasks: Mapped[list["Task"]] = relationship(
        "Task",
        back_populates="column",
        cascade="all, delete-orphan",
        order_by="Task.position",
    )


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("length(title) > 0", name="check_task_title_length"),
        Index("idx_tasks_column_position", "column_id", "position"),
        Index("idx_tasks_project", "project_id"),
        Index("idx_tasks_project_updated", "project_id", "updated_at"),
        Index("idx_tasks_assignee", "assignee_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[TaskPriority | None] = mapped_column(
        SQLEnum(
            TaskPriority,
            native_enum=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=True,
    )
    position: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    column_id: Mapped[int] = mapped_column(ForeignKey("board_columns.id", ondelete="CASCADE"))

    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    column: Mapped["BoardColumn"] = relationship(back_populates="tasks")
    assignee: Mapped["User"] = relationship("User", foreign_keys=[assignee_id])
    author: Mapped["User"] = relationship("User", foreign_keys=[author_id])

    tags: Mapped[list["Tag"]] = relationship("Tag", secondary=task_tags, back_populates="tasks")
