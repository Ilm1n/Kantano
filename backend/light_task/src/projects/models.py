from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.db.mixins import TimestampMixin
from src.projects.constants import ProjectRole

if TYPE_CHECKING:
    from src.boards.models import BoardColumn
    from src.tags.models import Tag
    from src.users.models import User


class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    __table_args__ = (CheckConstraint("length(name) > 0", name="check_project_name_length"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str] = mapped_column(
        String(9), default="#3B82F6", server_default="#3B82F6", nullable=False
    )
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
    )

    members: Mapped[list["ProjectMember"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    board_columns: Mapped[list["BoardColumn"]] = relationship(
        "BoardColumn",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="BoardColumn.position",
    )

    tags: Mapped[list["Tag"]] = relationship(
        "Tag",
        back_populates="project",
        cascade="all, delete-orphan",
    )


class ProjectMember(Base, TimestampMixin):
    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="idx_unique_project_user"),
        Index("idx_project_members_user", "user_id"),
        Index("idx_project_members_project_joined", "project_id", "joined_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    role: Mapped[ProjectRole] = mapped_column(
        Enum(ProjectRole, native_enum=False),
        nullable=False,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    project: Mapped["Project"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(
        "User",
        back_populates="project_memberships",
    )
