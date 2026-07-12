from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    from ..base import Base  # type: ignore
except Exception:  # pragma: no cover
    from sqlalchemy.orm import DeclarativeBase

    class Base(DeclarativeBase):
        pass


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    module: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="P2", index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    due_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    branch: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    related_issue: Mapped[str | None] = mapped_column(String(100), nullable=True)

    assignee_agent_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("agents.id"), nullable=True, index=True
    )
    reviewers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped["Project"] = relationship(back_populates="tasks")
    assignee_agent: Mapped["Agent | None"] = relationship(back_populates="tasks")
    events: Mapped[list["TaskEvent"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    dispatches: Mapped[list["TaskDispatch"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    handoffs: Mapped[list["Handoff"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    approvals: Mapped[list["Approval"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    context_health_records: Mapped[list["ContextHealthRecord"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )

    @property
    def latest_dispatch(self) -> "TaskDispatch | None":
        dispatches = list(self.dispatches or [])
        if not dispatches:
            return None
        dispatches.sort(key=lambda item: item.created_at or 0, reverse=True)
        return dispatches[0]


from .project import Project  # noqa: E402
from .agent import Agent  # noqa: E402
from .task_event import TaskEvent  # noqa: E402
from .task_dispatch import TaskDispatch  # noqa: E402
from .handoff import Handoff  # noqa: E402
from .approval import Approval  # noqa: E402
from .context_health import ContextHealthRecord  # noqa: E402
