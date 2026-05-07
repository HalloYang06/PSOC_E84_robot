from __future__ import annotations

import uuid

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    from ..base import Base  # type: ignore
except Exception:  # pragma: no cover
    from sqlalchemy.orm import DeclarativeBase

    class Base(DeclarativeBase):
        pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_seen_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    memberships: Mapped[list["ProjectMember"]] = relationship("ProjectMember", back_populates="user")
    sent_invites: Mapped[list["ProjectInvite"]] = relationship(
        "ProjectInvite",
        foreign_keys="ProjectInvite.invited_by_user_id",
        back_populates="invited_by_user",
    )
    accepted_invites: Mapped[list["ProjectInvite"]] = relationship(
        "ProjectInvite",
        foreign_keys="ProjectInvite.accepted_by_user_id",
        back_populates="accepted_by_user",
    )
