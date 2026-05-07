from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.common.response import ok
from app.db.session import get_db
from app.modules.read_access import require_project_read_access

from .schemas import DevelopmentWorkshopFrameworkRead
from .service import get_development_framework


router = APIRouter(prefix="/api/development", tags=["development"])


@router.get("/framework")
def api_get_global_development_framework():
    payload = get_development_framework()
    return ok(DevelopmentWorkshopFrameworkRead.model_validate(payload).model_dump(mode="json"))


@router.get("/projects/{project_id}/framework")
def api_get_project_development_framework(project_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="development.framework.read")
    payload = get_development_framework(project_id)
    return ok(DevelopmentWorkshopFrameworkRead.model_validate(payload).model_dump(mode="json"))

