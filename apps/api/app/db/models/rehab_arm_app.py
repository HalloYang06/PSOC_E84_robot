from __future__ import annotations

import uuid

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base


class RehabAppUserProfile(Base):
    __tablename__ = "rehab_app_user_profiles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="patient", index=True)
    affected_side: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    rehab_stage: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    medical_constraints: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    pain_baseline: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RehabAppDeviceBinding(Base):
    __tablename__ = "rehab_app_device_bindings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    m33_device_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    ble_name: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    firmware_version: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    trust_status: Mapped[str] = mapped_column(String(40), nullable=False, default="unverified", index=True)
    platform_project_id: Mapped[str] = mapped_column(String(36), nullable=False, default="", index=True)
    bound_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    syncs: Mapped[list["RehabAppTrainingPlanSync"]] = relationship(back_populates="device")


class RehabAppTrainingPlan(Base):
    __tablename__ = "rehab_app_training_plans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="manual", index=True)
    goal: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_joints: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    movement_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    sets: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reps: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    duration_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_angle_range: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    speed_level: Mapped[str] = mapped_column(String(40), nullable=False, default="slow")
    assist_level: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    emg_policy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    safety_constraints: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    syncs: Mapped[list["RehabAppTrainingPlanSync"]] = relationship(back_populates="plan")


class RehabAppTrainingPlanSync(Base):
    __tablename__ = "rehab_app_training_plan_syncs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    plan_id: Mapped[str] = mapped_column(String(64), ForeignKey("rehab_app_training_plans.id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(64), ForeignKey("rehab_app_device_bindings.id"), nullable=False, index=True)
    sync_status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)
    m33_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    synced_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())

    plan: Mapped[RehabAppTrainingPlan] = relationship(back_populates="syncs")
    device: Mapped[RehabAppDeviceBinding] = relationship(back_populates="syncs")


class RehabAppTrainingSession(Base):
    __tablename__ = "rehab_app_training_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    plan_id: Mapped[str] = mapped_column(String(64), ForeignKey("rehab_app_training_plans.id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(64), ForeignKey("rehab_app_device_bindings.id"), nullable=False, index=True)
    started_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="started", index=True)
    completion_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    interruption_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_assist_level: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_assist_level: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    m33_reject_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pain_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    user_note: Mapped[str] = mapped_column(Text, nullable=False, default="")


class RehabAppEmgSummary(Base):
    __tablename__ = "rehab_app_emg_summaries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("rehab_app_training_sessions.id"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    muscle_name: Mapped[str] = mapped_column(String(120), nullable=False)
    rms_avg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    peak: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    activation_avg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    fatigue_index: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    contact_quality: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RehabAppIntentInferenceSummary(Base):
    __tablename__ = "rehab_app_intent_inference_summaries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("rehab_app_training_sessions.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="m55")
    predicted_action: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    topk: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    stability_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
