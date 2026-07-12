from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.common.access import resolve_project_write_principal
from app.common.response import ok
from app.db.session import get_db
from app.modules.read_access import require_project_read_access

from .schemas import BossPlanCreate, BossPlanItemUpdate, BossPlanRead
from .service import create_boss_plan, get_boss_plan_or_404, list_boss_plans, update_boss_plan_item


router = APIRouter(prefix="/api/projects/{project_id}/boss-plans", tags=["boss-plans"])


@router.get("")
def api_list_boss_plans(project_id: str, request: Request, limit: int = 30, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="boss_plans.read")
    return ok([BossPlanRead.model_validate(item).model_dump(mode="json", by_alias=True) for item in list_boss_plans(db, project_id, limit=limit)])


@router.get("/{plan_id}")
def api_get_boss_plan(project_id: str, plan_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="boss_plans.read")
    return ok(BossPlanRead.model_validate(get_boss_plan_or_404(db, project_id, plan_id)).model_dump(mode="json", by_alias=True))


@router.post("")
def api_create_boss_plan(project_id: str, payload: BossPlanCreate, request: Request, db: Session = Depends(get_db)):
    resolve_project_write_principal(db, request, project_id, require_privileged=False, action="boss_plans.write")
    item = create_boss_plan(db, project_id, payload)
    return ok(BossPlanRead.model_validate(item).model_dump(mode="json", by_alias=True))


@router.patch("/{plan_id}/items/{item_id}")
def api_update_boss_plan_item(
    project_id: str,
    plan_id: str,
    item_id: str,
    payload: BossPlanItemUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    resolve_project_write_principal(db, request, project_id, require_privileged=False, action="boss_plans.write")
    item = update_boss_plan_item(db, project_id, plan_id, item_id, payload)
    return ok(BossPlanRead.model_validate(item).model_dump(mode="json", by_alias=True))
