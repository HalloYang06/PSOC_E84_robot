from __future__ import annotations

import uuid

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    from ..base import Base  # type: ignore
except Exception:  # pragma: no cover
    from sqlalchemy.orm import DeclarativeBase

    class Base(DeclarativeBase):
        pass


class ContextHealthRecord(Base):
    __tablename__ = "context_health_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    task_id: Mapped[str] = mapped_column(String(64), ForeignKey("tasks.id"), nullable=False, index=True)
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    usage_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    health: Mapped[str] = mapped_column(String(16), nullable=False, default="green", index=True)
    conversation_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_loaded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped["Task"] = relationship(back_populates="context_health_records")


from .task import Task  # noqa: E402
