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


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    message_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    sender_type: Mapped[str] = mapped_column(String(16), nullable=False, default="system", index=True)
    sender_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    parent_message_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("messages.id"), nullable=True, index=True)
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    parent: Mapped["Message | None"] = relationship("Message", remote_side=[id])
