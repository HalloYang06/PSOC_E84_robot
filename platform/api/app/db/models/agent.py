from __future__ import annotations

import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    from ..base import Base  # type: ignore
except Exception:  # pragma: no cover
    from sqlalchemy.orm import DeclarativeBase

    class Base(DeclarativeBase):
        pass


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    role: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)

    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="manual_codex_thread", index=True)
    execution_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    agent_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    responsibility: Mapped[str | None] = mapped_column(Text, nullable=True)
    modules: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    runner_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("runners.id"), nullable=True, index=True)
    runner_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    permission_level: Mapped[str] = mapped_column(String(8), nullable=False, default="L2", index=True)
    read_paths: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    write_paths: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    max_tokens_per_task: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_cost_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    runner: Mapped["Runner | None"] = relationship(back_populates="agents")
    tasks: Mapped[list["Task"]] = relationship(back_populates="assignee_agent")


from .runner import Runner  # noqa: E402
from .task import Task  # noqa: E402
