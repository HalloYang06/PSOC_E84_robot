from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import AppError
from app.db.models.project import Project
from app.db.models.project_knowledge import ProjectKnowledgeDocument, ProjectSkill, SeatSkillAssignment
from app.db.models.project_collaboration import ProjectThreadWorkstation

from .schemas import KnowledgeDocumentCreate, ProjectSkillCreate, SeatSkillAssignmentCreate


_WINDOWS_DRIVE_RE = re.compile(r"^[a-zA-Z]:[\\/]")


def normalize_repo_relative_path(value: str | None, *, required: bool = True) -> str | None:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        if required:
            raise AppError("BAD_REPO_PATH", "GitHub 知识库路径不能为空", status_code=422)
        return None
    if raw.startswith(("http://", "https://", "file://")) or raw.startswith("/") or _WINDOWS_DRIVE_RE.match(raw):
        raise AppError("BAD_REPO_PATH", "知识库路径必须是 GitHub 仓库相对路径，不能是本地绝对路径或 URL", status_code=422)
    parts = [part for part in raw.split("/") if part]
    if any(part in {".", ".."} for part in parts):
        raise AppError("BAD_REPO_PATH", "知识库路径不能包含 . 或 ..", status_code=422)
    if not parts:
        if required:
            raise AppError("BAD_REPO_PATH", "GitHub 知识库路径不能为空", status_code=422)
        return None
    return "/".join(parts)


def _project_or_404(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
    return project


def _now_if_exists_flag(payload_time: datetime | None, exists_in_repo: bool | None) -> datetime | None:
    if payload_time is not None:
        return payload_time
    if exists_in_repo is True:
        return datetime.now(timezone.utc)
    return None


def upsert_knowledge_document(db: Session, project_id: str, payload: KnowledgeDocumentCreate) -> ProjectKnowledgeDocument:
    _project_or_404(db, project_id)
    path = normalize_repo_relative_path(payload.repo_relative_path, required=True)
    assert path is not None
    row = db.scalar(
        select(ProjectKnowledgeDocument).where(
            ProjectKnowledgeDocument.project_id == project_id,
            ProjectKnowledgeDocument.repo_relative_path == path,
        )
    )
    if row is None:
        row = ProjectKnowledgeDocument(project_id=project_id, title=payload.title, repo_relative_path=path)
    row.title = payload.title
    row.source_url = payload.source_url
    row.scope = (payload.scope or "project").strip() or "project"
    row.owner_type = (payload.owner_type or "").strip() or None
    row.owner_id = (payload.owner_id or "").strip() or None
    row.exists_in_repo = payload.exists_in_repo
    row.version_ref = (payload.version_ref or "").strip() or None
    row.summary = payload.summary
    row.tags = payload.tags or None
    row.last_synced_at = _now_if_exists_flag(payload.last_synced_at, payload.exists_in_repo)
    row.extra_data = payload.metadata or None
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_knowledge_documents(db: Session, project_id: str) -> list[ProjectKnowledgeDocument]:
    _project_or_404(db, project_id)
    return list(
        db.scalars(
            select(ProjectKnowledgeDocument)
            .where(ProjectKnowledgeDocument.project_id == project_id)
            .order_by(ProjectKnowledgeDocument.scope.asc(), ProjectKnowledgeDocument.repo_relative_path.asc())
        )
    )


def upsert_project_skill(db: Session, project_id: str, payload: ProjectSkillCreate) -> ProjectSkill:
    _project_or_404(db, project_id)
    skill_id = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", payload.skill_id.strip()).strip("-")
    if not skill_id:
        raise AppError("BAD_SKILL_ID", "skill_id 不能为空", status_code=422)
    path = normalize_repo_relative_path(payload.repo_relative_path, required=False)
    row = db.scalar(select(ProjectSkill).where(ProjectSkill.project_id == project_id, ProjectSkill.skill_id == skill_id))
    if row is None:
        row = ProjectSkill(project_id=project_id, skill_id=skill_id, label=payload.label)
    row.label = payload.label
    row.source = (payload.source or "custom").strip() or "custom"
    row.category = (payload.category or "").strip() or None
    row.repo_relative_path = path
    row.source_url = payload.source_url
    row.description = payload.description
    row.recommended_for = payload.recommended_for or None
    row.exists_in_repo = payload.exists_in_repo
    row.version_ref = (payload.version_ref or "").strip() or None
    row.last_synced_at = _now_if_exists_flag(payload.last_synced_at, payload.exists_in_repo)
    row.extra_data = payload.metadata or None
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_project_skills(db: Session, project_id: str) -> list[ProjectSkill]:
    _project_or_404(db, project_id)
    return list(
        db.scalars(
            select(ProjectSkill)
            .where(ProjectSkill.project_id == project_id)
            .order_by(ProjectSkill.category.asc().nulls_last(), ProjectSkill.label.asc())
        )
    )


def assign_seat_skill(db: Session, project_id: str, payload: SeatSkillAssignmentCreate) -> SeatSkillAssignment:
    _project_or_404(db, project_id)
    seat_id = payload.seat_id.strip()
    skill_id = payload.skill_id.strip()
    seat = db.scalar(
        select(ProjectThreadWorkstation).where(
            ProjectThreadWorkstation.project_id == project_id,
            (ProjectThreadWorkstation.id == seat_id)
            | (ProjectThreadWorkstation.config_id == seat_id)
            | (ProjectThreadWorkstation.name == seat_id)
            | (ProjectThreadWorkstation.agent_id == seat_id),
        )
    )
    if seat is None:
        raise AppError("SEAT_NOT_FOUND", "NPC 不存在或不属于该项目", status_code=404)
    skill = db.scalar(select(ProjectSkill).where(ProjectSkill.project_id == project_id, ProjectSkill.skill_id == skill_id))
    if skill is None:
        raise AppError("SKILL_NOT_FOUND", "Skill 不存在或不属于该项目", status_code=404)
    row = db.scalar(
        select(SeatSkillAssignment).where(
            SeatSkillAssignment.project_id == project_id,
            SeatSkillAssignment.seat_id == seat.id,
            SeatSkillAssignment.skill_id == skill.skill_id,
        )
    )
    if row is None:
        row = SeatSkillAssignment(project_id=project_id, seat_id=seat.id, skill_id=skill.skill_id)
    row.assignment_type = (payload.assignment_type or "direct").strip() or "direct"
    row.status = (payload.status or "active").strip() or "active"
    row.notes = payload.notes
    row.extra_data = payload.metadata or None
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_seat_skill_assignments(db: Session, project_id: str, seat_id: str | None = None) -> list[SeatSkillAssignment]:
    _project_or_404(db, project_id)
    stmt = select(SeatSkillAssignment).where(SeatSkillAssignment.project_id == project_id)
    if seat_id:
        stmt = stmt.where(SeatSkillAssignment.seat_id == seat_id)
    return list(db.scalars(stmt.order_by(SeatSkillAssignment.seat_id.asc(), SeatSkillAssignment.skill_id.asc())))
