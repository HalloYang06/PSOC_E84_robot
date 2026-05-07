from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    from ..base import Base  # type: ignore
except Exception:  # pragma: no cover
    from sqlalchemy.orm import DeclarativeBase

    class Base(DeclarativeBase):
        pass


class Requirement(Base):
    __tablename__ = "requirements"
    __table_args__ = (
        Index(
            "uq_requirements_follow_up_from_requirement_id",
            "follow_up_from_requirement_id",
            unique=True,
            sqlite_where=text("follow_up_from_requirement_id IS NOT NULL"),
            postgresql_where=text("follow_up_from_requirement_id IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    title: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    requirement_type: Mapped[str] = mapped_column(String(64), nullable=False, default="thread_request", index=True)
    module: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="high", index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="waiting_response", index=True)

    from_agent: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    to_agent: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    follow_up_from_requirement_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    target_seat_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    trigger_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="manual", index=True)
    dependency_requirement_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    context_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_files: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    max_response_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=3000)

    response_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_response_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["RequirementMessage"]] = relationship(
        back_populates="requirement", cascade="all, delete-orphan"
    )


class RequirementMessage(Base):
    __tablename__ = "requirement_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    requirement_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("requirements.id"), nullable=False, index=True
    )

    sender_type: Mapped[str] = mapped_column(String(16), nullable=False, default="agent", index=True)
    sender_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status_after_reply: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())

    requirement: Mapped["Requirement"] = relationship(back_populates="messages")
