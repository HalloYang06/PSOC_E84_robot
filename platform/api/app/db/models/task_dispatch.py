from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    from ..base import Base  # type: ignore
except Exception:  # pragma: no cover
    from sqlalchemy.orm import DeclarativeBase

    class Base(DeclarativeBase):
        pass


class TaskDispatch(Base):
    __tablename__ = "task_dispatches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(64), ForeignKey("tasks.id"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False, index=True)

    workstation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    workstation_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("agents.id"), nullable=True, index=True)
    computer_node_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ai_provider_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    runner_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("runners.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="dispatched", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    dispatched_by_user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id"), nullable=True, index=True)

    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    task: Mapped["Task"] = relationship("Task", back_populates="dispatches")
    project: Mapped["Project"] = relationship("Project")
    agent: Mapped["Agent | None"] = relationship("Agent")
    runner: Mapped["Runner | None"] = relationship("Runner")
    dispatched_by_user: Mapped["User | None"] = relationship("User")


from .agent import Agent  # noqa: E402
from .project import Project  # noqa: E402
from .runner import Runner  # noqa: E402
from .task import Task  # noqa: E402
from .user import User  # noqa: E402
