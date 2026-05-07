from __future__ import annotations

import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    from ..base import Base  # type: ignore
except Exception:  # pragma: no cover
    from sqlalchemy.orm import DeclarativeBase

    class Base(DeclarativeBase):
        pass


class ProjectAIProvider(Base):
    __tablename__ = "project_ai_providers"
    __table_args__ = (UniqueConstraint("project_id", "config_id", name="uq_project_ai_providers_project_config_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    config_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    label: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    endpoint: Mapped[str | None] = mapped_column(String(500), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project: Mapped["Project"] = relationship("Project", back_populates="ai_providers")


class ProjectComputerNode(Base):
    __tablename__ = "project_computer_nodes"
    __table_args__ = (UniqueConstraint("project_id", "config_id", name="uq_project_computer_nodes_project_config_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    config_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    label: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="offline", index=True)
    runner_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("runners.id"), nullable=True, index=True)
    host: Mapped[str | None] = mapped_column(String(200), nullable=True)
    os: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project: Mapped["Project"] = relationship("Project", back_populates="computer_nodes")
    runner: Mapped["Runner | None"] = relationship("Runner")


class ProjectThreadWorkstation(Base):
    __tablename__ = "project_thread_workstations"
    __table_args__ = (UniqueConstraint("project_id", "config_id", name="uq_project_thread_workstations_project_config_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    config_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("agents.id"), nullable=True, index=True)
    computer_node_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ai_provider_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="idle", index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project: Mapped["Project"] = relationship("Project", back_populates="thread_workstations")
    agent: Mapped["Agent | None"] = relationship("Agent")


from .agent import Agent  # noqa: E402
from .project import Project  # noqa: E402
from .runner import Runner  # noqa: E402
