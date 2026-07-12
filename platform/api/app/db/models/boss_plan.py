from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base


class BossPlan(Base):
    __tablename__ = "boss_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    boss_seat_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(240), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    source_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    contract_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    items: Mapped[list["BossPlanItem"]] = relationship(
        "BossPlanItem",
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="BossPlanItem.sort_order",
    )


class BossPlanItem(Base):
    __tablename__ = "boss_plan_items"
    __table_args__ = (
        UniqueConstraint("plan_id", "role", "target_seat_id", name="uq_boss_plan_items_plan_role_target"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("boss_plans.id"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(160), nullable=False)
    target_seat_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    target_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned", index=True)
    dispatch_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    receipt_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)
    skills: Mapped[list | None] = mapped_column(JSON, nullable=True)
    knowledge_paths: Mapped[list | None] = mapped_column(JSON, nullable=True)
    acceptance: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    plan: Mapped[BossPlan] = relationship("BossPlan", back_populates="items")
