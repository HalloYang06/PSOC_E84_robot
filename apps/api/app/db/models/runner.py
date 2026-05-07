from __future__ import annotations

import uuid

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    from ..base import Base  # type: ignore
except Exception:  # pragma: no cover
    from sqlalchemy.orm import DeclarativeBase

    class Base(DeclarativeBase):
        pass


class Runner(Base):
    __tablename__ = "runners"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    host: Mapped[str | None] = mapped_column(String(200), nullable=True)
    os: Mapped[str | None] = mapped_column(String(64), nullable=True)

    capabilities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="offline", index=True)

    allow_hardware_access: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_concurrent_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    last_heartbeat_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    agents: Mapped[list["Agent"]] = relationship(back_populates="runner")


from .agent import Agent  # noqa: E402  (relationship target)
