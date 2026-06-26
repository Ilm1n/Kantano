from typing import TYPE_CHECKING

from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.boards.models import Task
    from src.projects.models import Project


task_tags = Table(
    "task_tags",
    Base.metadata,
    Column("task_id", Integer, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

Index("idx_task_tags_tag_task", task_tags.c.tag_id, task_tags.c.task_id)


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("project_id", "name", name="idx_unique_project_tag_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    color: Mapped[str] = mapped_column(String(9), default="#9CA3AF", server_default="#9CA3AF")

    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))

    project: Mapped["Project"] = relationship("Project", back_populates="tags")

    tasks: Mapped[list["Task"]] = relationship("Task", secondary=task_tags, back_populates="tags")
