from __future__ import annotations

import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    from ..base import Base  # type: ignore
except Exception:  # pragma: no cover
    from sqlalchemy.orm import DeclarativeBase

    class Base(DeclarativeBase):
        pass


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    role: Mapped[str] = mapped_column(String(64), nullable=False, default="member", index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    is_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_project_seen_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_project_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    joined_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project: Mapped["Project"] = relationship("Project")
    user: Mapped["User"] = relationship("User", back_populates="memberships")
