from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.project import Project

from .schemas import ProjectCreate, ProjectUpdate


def list_projects(db: Session) -> list[Project]:
    return list(db.scalars(select(Project).order_by(Project.created_at.desc())))


def get_project(db: Session, project_id: str) -> Project | None:
    return db.get(Project, project_id)


def create_project(db: Session, payload: ProjectCreate) -> Project:
    project = Project(**payload.model_dump())
    db.add(project)
    db.flush()
    return project


def update_project(db: Session, project: Project, payload: ProjectUpdate) -> Project:
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    db.add(project)
    db.flush()
    return project
