from __future__ import annotations

import uuid

from sqlalchemy import DateTime, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    from ..base import Base  # type: ignore
except Exception:  # pragma: no cover
    from sqlalchemy.orm import DeclarativeBase

    class Base(DeclarativeBase):
        pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    requirement_policy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    collaboration_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    github_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    local_git_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    default_branch: Mapped[str] = mapped_column(String(100), nullable=False, default="main")
    develop_branch: Mapped[str] = mapped_column(String(100), nullable=False, default="develop")

    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tasks: Mapped[list["Task"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    ai_providers: Mapped[list["ProjectAIProvider"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    computer_nodes: Mapped[list["ProjectComputerNode"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    thread_workstations: Mapped[list["ProjectThreadWorkstation"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    workstations: Mapped[list["ProjectWorkstation"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


from .task import Task  # noqa: E402  (relationship target)
from .project_collaboration import ProjectAIProvider, ProjectComputerNode, ProjectThreadWorkstation, ProjectWorkstation  # noqa: E402
