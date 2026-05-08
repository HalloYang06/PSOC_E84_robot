from __future__ import annotations

import uuid

from sqlalchemy import DateTime, Index, JSON, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

try:
    from ..base import Base  # type: ignore
except Exception:  # pragma: no cover
    from sqlalchemy.orm import DeclarativeBase

    class Base(DeclarativeBase):
        pass


class CollaborationMessage(Base):
    __tablename__ = "collaboration_messages"
    __table_args__ = (
        Index(
            "uq_collaboration_messages_dedupe_key",
            "dedupe_key",
            unique=True,
            sqlite_where=text("dedupe_key IS NOT NULL"),
            postgresql_where=text("dedupe_key IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    approval_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    handoff_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    requirement_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    dispatch_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    message_type: Mapped[str] = mapped_column(String(32), nullable=False, default="comment_message", index=True)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    sender_type: Mapped[str] = mapped_column(String(16), nullable=False, default="human", index=True)
    sender_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    recipient_type: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    recipient_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open", index=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
