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


def _clean_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = re.split(r"[\n,]", value)
    else:
        raw_items = []
    seen: set[str] = set()
    items: list[str] = []
    for item in raw_items:
        text = str(item or "").strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            items.append(text)
    return items


def _remove_skill_from_seat_metadata(db: Session, project_id: str, skill_id: str) -> None:
    normalized = str(skill_id or "").strip().lower()
    if not normalized:
        return
    seats = list(db.scalars(select(ProjectThreadWorkstation).where(ProjectThreadWorkstation.project_id == project_id)))
    for seat in seats:
        metadata = dict(seat.extra_data or {}) if isinstance(seat.extra_data, dict) else {}
        changed = False
        for key in ("skill_loadout", "skillLoadout", "additional_skill_ids", "additionalSkillIds"):
            current = _clean_string_list(metadata.get(key))
            if not current:
                continue
            next_values = [item for item in current if item.lower() != normalized]
            if next_values != current:
                metadata[key] = next_values
                changed = True
        snapshot = metadata.get("skill_forge_snapshot")
        if isinstance(snapshot, dict) and str(snapshot.get("changed_skill_id") or "").strip().lower() == normalized:
            metadata["skill_forge_snapshot"] = {
                **snapshot,
                "removed_at": datetime.now(timezone.utc).isoformat(),
                "summary": "该 Skill 已从项目能力库删除，后续上岗包不会继续读取它。",
            }
            changed = True
        if changed:
            seat.extra_data = metadata or None
            db.add(seat)


def _remove_skill_from_project_config(db: Session, project: Project, skill_id: str) -> None:
    normalized = str(skill_id or "").strip().lower()
    if not normalized:
        return
    config = dict(project.collaboration_config or {}) if isinstance(project.collaboration_config, dict) else {}
    library = config.get("skill_library")
    if not isinstance(library, list):
        return
    next_library = [
        item
        for item in library
        if not (isinstance(item, dict) and str(item.get("id") or item.get("skill_id") or "").strip().lower() == normalized)
    ]
    if len(next_library) != len(library):
        project.collaboration_config = {**config, "skill_library": next_library}
        db.add(project)


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


def delete_knowledge_document(db: Session, project_id: str, document_id: str) -> None:
    _project_or_404(db, project_id)
    key = str(document_id or "").strip()
    if not key:
        raise AppError("DOCUMENT_ID_REQUIRED", "知识库条目不能为空", status_code=422)
    row = db.scalar(
        select(ProjectKnowledgeDocument).where(
            ProjectKnowledgeDocument.project_id == project_id,
            (ProjectKnowledgeDocument.id == key) | (ProjectKnowledgeDocument.repo_relative_path == key),
        )
    )
    if row is None:
        raise AppError("DOCUMENT_NOT_FOUND", "知识库条目不存在或不属于该项目", status_code=404)
    db.delete(row)
    db.commit()


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


def delete_project_skill(db: Session, project_id: str, skill_id: str) -> None:
    project = _project_or_404(db, project_id)
    key = str(skill_id or "").strip()
    if not key:
        raise AppError("SKILL_ID_REQUIRED", "Skill 不能为空", status_code=422)
    row = db.scalar(
        select(ProjectSkill).where(
            ProjectSkill.project_id == project_id,
            (ProjectSkill.id == key) | (ProjectSkill.skill_id == key),
        )
    )
    if row is None:
        raise AppError("SKILL_NOT_FOUND", "Skill 不存在或不属于该项目", status_code=404)
    db.query(SeatSkillAssignment).filter(
        SeatSkillAssignment.project_id == project_id,
        SeatSkillAssignment.skill_id == row.skill_id,
    ).delete(synchronize_session=False)
    _remove_skill_from_project_config(db, project, row.skill_id)
    _remove_skill_from_seat_metadata(db, project_id, row.skill_id)
    db.delete(row)
    db.commit()


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
