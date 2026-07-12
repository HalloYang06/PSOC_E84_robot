from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base


class ProjectKnowledgeDocument(Base):
    __tablename__ = "project_knowledge_documents"
    __table_args__ = (
        UniqueConstraint("project_id", "repo_relative_path", name="uq_project_knowledge_documents_project_path"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    repo_relative_path: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    source_url: Mapped[str | None] = mapped_column(String(700), nullable=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="project", index=True)
    owner_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    exists_in_repo: Mapped[bool | None] = mapped_column(nullable=True)
    version_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    last_synced_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project: Mapped["Project"] = relationship("Project", back_populates="knowledge_documents")


class ProjectSkill(Base):
    __tablename__ = "project_skills"
    __table_args__ = (UniqueConstraint("project_id", "skill_id", name="uq_project_skills_project_skill"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    skill_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="custom", index=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    repo_relative_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(700), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_for: Mapped[list | None] = mapped_column(JSON, nullable=True)
    exists_in_repo: Mapped[bool | None] = mapped_column(nullable=True)
    version_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_synced_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project: Mapped["Project"] = relationship("Project", back_populates="skills")


class SeatSkillAssignment(Base):
    __tablename__ = "seat_skill_assignments"
    __table_args__ = (
        UniqueConstraint("project_id", "seat_id", "skill_id", name="uq_seat_skill_assignments_project_seat_skill"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    seat_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    skill_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    assignment_type: Mapped[str] = mapped_column(String(32), nullable=False, default="direct", index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project: Mapped["Project"] = relationship("Project", back_populates="seat_skill_assignments")


from .project import Project  # noqa: E402
