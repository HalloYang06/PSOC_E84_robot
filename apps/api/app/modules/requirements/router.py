from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.common.access import resolve_project_write_principal_for_target
from app.common.errors import AppError
from app.common.response import ok
from app.db.models.task import Task
from app.db.session import get_db
from app.modules.messages.schemas import MessageCreate, MessageRead
from app.modules.messages.service import create_entity_message, list_entity_messages
from app.modules.collaboration.schemas import CollaborationMessageRead
from app.modules.read_access import (
    require_project_read_access,
    resolve_requirement_project_id,
    resolve_task_project_id,
    scoped_project_ids_for_read,
)

from .schemas import (
    NeedRouteRequest,
    RequirementActionRequest,
    RequirementCreate,
    RequirementDispatchRequest,
    RequirementFinalReplyRequest,
    RequirementMessageRead,
    RequirementPromoteRequest,
    RequirementRead,
    RequirementReplyCreate,
    RequirementRouteRequest,
    StructuredNeedCreate,
    RequirementUpdate,
)
from .service import (
    add_requirement_reply,
    add_requirement_final_reply,
    create_structured_need,
    create_requirement,
    dispatch_requirement,
    find_similar_requirements,
    get_requirement_or_404,
    list_requirements,
    preview_need_route,
    promote_requirement_to_knowledge,
    route_need_to_task,
    route_requirement,
    run_requirement_autonomy_sweep,
    run_requirement_action,
    update_requirement,
)


router = APIRouter(prefix="/api/requirements", tags=["requirements"])


def _requirement_project_id(db: Session, requirement_id: str) -> str:
    requirement = get_requirement_or_404(db, requirement_id)
    if requirement.project_id:
        return requirement.project_id
    if requirement.task_id:
        task = db.get(Task, requirement.task_id)
        if task is not None and task.project_id:
            return task.project_id
    raise AppError("PROJECT_NOT_FOUND", "requirement has no project context", status_code=404)


def _payload_project_id(db: Session, project_id: str | None, task_id: str | None) -> str:
    if project_id:
        return project_id
    if task_id:
        task = db.get(Task, task_id)
        if task is not None and task.project_id:
            return task.project_id
    raise AppError("VALIDATION_ERROR", "requirement write requires project_id or task_id", status_code=422)


@router.get("")
def api_list_requirements(
    project_id: list[str] | None = Query(None),
    request: Request = None,
    db: Session = Depends(get_db),
):
    scoped_project_ids = scoped_project_ids_for_read(db, request, project_id, action="requirement.read")
    items = list_requirements(db, project_ids=scoped_project_ids) if scoped_project_ids else []
    return ok([RequirementRead.model_validate(item).model_dump(mode="json") for item in items])


@router.post("")
def api_create_requirement(payload: RequirementCreate, request: Request, db: Session = Depends(get_db)):
    project_id = _payload_project_id(db, payload.project_id, payload.task_id)
    resolve_project_write_principal_for_target(db, request, project_id, action="requirement.create")
    item = create_requirement(db, payload)
    return ok(RequirementRead.model_validate(item).model_dump(mode="json"))


@router.post("/structured-need")
def api_create_structured_need(payload: StructuredNeedCreate, request: Request, db: Session = Depends(get_db)):
    resolve_project_write_principal_for_target(db, request, payload.project_id, action="requirement.structured_need.create")
    result = create_structured_need(db, payload)
    route_result = result.get("route_result") if isinstance(result.get("route_result"), dict) else None
    return ok(
        {
            "requirement": RequirementRead.model_validate(result["requirement"]).model_dump(mode="json"),
            "route_preview": result["route_preview"],
            "route_result": None
            if route_result is None
            else {
                "requirement": RequirementRead.model_validate(route_result["requirement"]).model_dump(mode="json"),
                "route_preview": route_result["route_preview"],
                "task": None
                if route_result.get("task") is None
                else {
                    "id": route_result["task"].id,
                    "title": route_result["task"].title,
                    "status": route_result["task"].status,
                    "assignee_agent_id": route_result["task"].assignee_agent_id,
                },
                "dispatch": None
                if route_result.get("dispatch") is None
                else {
                    "id": route_result["dispatch"].id,
                    "status": route_result["dispatch"].status,
                    "workstation_id": route_result["dispatch"].workstation_id,
                    "runner_id": route_result["dispatch"].runner_id,
                },
            },
        }
    )


@router.get("/similar")
def api_similar_requirements(
    title: str | None = None,
    module: str | None = None,
    task_id: str | None = None,
    project_id: list[str] | None = Query(None),
    request: Request = None,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    scoped_project_ids = scoped_project_ids_for_read(db, request, project_id, action="requirement.similar")
    if task_id:
        task_project_id = resolve_task_project_id(db, task_id)
        require_project_read_access(db, request, task_project_id, action="requirement.similar")
        if task_project_id not in scoped_project_ids:
            scoped_project_ids = [task_project_id, *scoped_project_ids]
    items = (
        find_similar_requirements(
            db,
            title=title,
            module=module,
            task_id=task_id,
            project_ids=scoped_project_ids,
            limit=limit,
        )
        if scoped_project_ids
        else []
    )
    return ok([RequirementRead.model_validate(item).model_dump(mode="json") for item in items])


@router.post("/projects/{project_id}/autonomy-sweep")
def api_requirement_autonomy_sweep(project_id: str, request: Request, db: Session = Depends(get_db)):
    principal = resolve_project_write_principal_for_target(db, request, project_id, action="requirement.autonomy_sweep")
    result = run_requirement_autonomy_sweep(
        db,
        project_id,
        actor_type="human",
        actor_id=principal.user_id or "human-chief",
    )
    return ok(result)


@router.get("/{requirement_id}")
def api_get_requirement(requirement_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, resolve_requirement_project_id(db, requirement_id), action="requirement.read")
    item = get_requirement_or_404(db, requirement_id)
    return ok(RequirementRead.model_validate(item).model_dump(mode="json"))


@router.patch("/{requirement_id}")
def api_update_requirement(requirement_id: str, payload: RequirementUpdate, request: Request, db: Session = Depends(get_db)):
    project_id = (
        _payload_project_id(db, payload.project_id, payload.task_id)
        if (payload.project_id or payload.task_id)
        else _requirement_project_id(db, requirement_id)
    )
    resolve_project_write_principal_for_target(db, request, project_id, action="requirement.update")
    item = update_requirement(db, requirement_id, payload)
    return ok(RequirementRead.model_validate(item).model_dump(mode="json"))


@router.post("/{requirement_id}/reply")
@router.post("/{requirement_id}/respond")
def api_reply_requirement(requirement_id: str, payload: RequirementReplyCreate, request: Request, db: Session = Depends(get_db)):
    project_id = _requirement_project_id(db, requirement_id)
    resolve_project_write_principal_for_target(db, request, project_id, action="requirement.reply")
    reply = add_requirement_reply(db, requirement_id, payload)
    return ok(RequirementMessageRead.model_validate(reply).model_dump(mode="json"))


@router.post("/{requirement_id}/route")
def api_route_requirement(requirement_id: str, payload: RequirementRouteRequest, request: Request, db: Session = Depends(get_db)):
    project_id = _requirement_project_id(db, requirement_id)
    resolve_project_write_principal_for_target(db, request, project_id, action="requirement.route")
    item = route_requirement(db, requirement_id, payload)
    return ok(RequirementRead.model_validate(item).model_dump(mode="json"))


@router.get("/{requirement_id}/route-preview")
def api_preview_need_route(requirement_id: str, target_seat_id: str | None = None, request: Request = None, db: Session = Depends(get_db)):
    require_project_read_access(db, request, resolve_requirement_project_id(db, requirement_id), action="requirement.route_preview.read")
    return ok(preview_need_route(db, requirement_id, target_seat_id=target_seat_id))


@router.post("/{requirement_id}/route-to-task")
def api_route_need_to_task(requirement_id: str, payload: NeedRouteRequest, request: Request, db: Session = Depends(get_db)):
    project_id = _requirement_project_id(db, requirement_id)
    principal = resolve_project_write_principal_for_target(db, request, project_id, action="requirement.route_to_task")
    payload = payload.model_copy(update={"actor_type": "human", "actor_id": principal.user_id})
    result = route_need_to_task(db, requirement_id, payload)
    return ok(
        {
            "requirement": RequirementRead.model_validate(result["requirement"]).model_dump(mode="json"),
            "route_preview": result["route_preview"],
            "task": None
            if result.get("task") is None
            else {
                "id": result["task"].id,
                "title": result["task"].title,
                "status": result["task"].status,
                "assignee_agent_id": result["task"].assignee_agent_id,
            },
            "dispatch": None
            if result.get("dispatch") is None
            else {
                "id": result["dispatch"].id,
                "status": result["dispatch"].status,
                "workstation_id": result["dispatch"].workstation_id,
                "runner_id": result["dispatch"].runner_id,
            },
        }
    )


@router.post("/{requirement_id}/dispatch")
def api_dispatch_requirement(
    requirement_id: str,
    payload: RequirementDispatchRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    project_id = _requirement_project_id(db, requirement_id)
    principal = resolve_project_write_principal_for_target(db, request, project_id, action="requirement.dispatch")
    result = dispatch_requirement(
        db,
        requirement_id,
        payload.model_copy(update={"actor_type": "human", "actor_id": principal.user_id}),
    )
    return ok(
        {
            "requirement": RequirementRead.model_validate(result["requirement"]).model_dump(mode="json"),
            "message": CollaborationMessageRead.model_validate(result["message"]).model_dump(mode="json"),
        }
    )


@router.post("/{requirement_id}/final-reply")
def api_requirement_final_reply(
    requirement_id: str,
    payload: RequirementFinalReplyRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    project_id = _requirement_project_id(db, requirement_id)
    resolve_project_write_principal_for_target(db, request, project_id, action="requirement.final_reply")
    result = add_requirement_final_reply(db, requirement_id, payload)
    return ok(
        {
            "reply": RequirementMessageRead.model_validate(result["reply"]).model_dump(mode="json"),
            "message": CollaborationMessageRead.model_validate(result["message"]).model_dump(mode="json"),
        }
    )


@router.post("/{requirement_id}/accept")
def api_accept_requirement(requirement_id: str, payload: RequirementActionRequest, request: Request, db: Session = Depends(get_db)):
    project_id = _requirement_project_id(db, requirement_id)
    resolve_project_write_principal_for_target(
        db,
        request,
        project_id,
        require_privileged=True,
        action="requirement.accept",
    )
    item = run_requirement_action(db, requirement_id, "accept", payload)
    return ok(RequirementRead.model_validate(item).model_dump(mode="json"))


@router.post("/{requirement_id}/escalate")
def api_escalate_requirement(requirement_id: str, payload: RequirementActionRequest, request: Request, db: Session = Depends(get_db)):
    project_id = _requirement_project_id(db, requirement_id)
    resolve_project_write_principal_for_target(
        db,
        request,
        project_id,
        require_privileged=True,
        action="requirement.escalate",
    )
    item = run_requirement_action(db, requirement_id, "escalate", payload)
    return ok(RequirementRead.model_validate(item).model_dump(mode="json"))


@router.post("/{requirement_id}/close")
def api_close_requirement(requirement_id: str, payload: RequirementActionRequest, request: Request, db: Session = Depends(get_db)):
    project_id = _requirement_project_id(db, requirement_id)
    resolve_project_write_principal_for_target(
        db,
        request,
        project_id,
        require_privileged=True,
        action="requirement.close",
    )
    item = run_requirement_action(db, requirement_id, "close", payload)
    return ok(RequirementRead.model_validate(item).model_dump(mode="json"))


@router.post("/{requirement_id}/promote-to-knowledge")
def api_promote_requirement(requirement_id: str, payload: RequirementPromoteRequest, request: Request, db: Session = Depends(get_db)):
    project_id = _requirement_project_id(db, requirement_id)
    resolve_project_write_principal_for_target(
        db,
        request,
        project_id,
        require_privileged=True,
        action="requirement.promote",
    )
    return ok(promote_requirement_to_knowledge(db, requirement_id, payload))


@router.get("/{requirement_id}/messages")
def api_requirement_messages(requirement_id: str, message_type: str | None = None, request: Request = None, db: Session = Depends(get_db)):
    require_project_read_access(
        db,
        request,
        resolve_requirement_project_id(db, requirement_id),
        action="requirement.messages.read",
    )
    items = list_entity_messages(db, "requirement", requirement_id, message_type=message_type)
    return ok([MessageRead.model_validate(item).model_dump(mode="json") for item in items])


@router.post("/{requirement_id}/messages")
def api_create_requirement_message(requirement_id: str, payload: MessageCreate, request: Request, db: Session = Depends(get_db)):
    project_id = payload.project_id or _requirement_project_id(db, requirement_id)
    resolve_project_write_principal_for_target(db, request, project_id, action="requirement.message.create")
    data = payload.model_dump()
    data["entity_type"] = "requirement"
    data["entity_id"] = requirement_id
    return ok(
        MessageRead.model_validate(
            create_entity_message(
                db,
                "requirement",
                requirement_id,
                project_id=data["project_id"],
                message_type=data["message_type"],
                sender_type=data["sender_type"],
                sender_id=data["sender_id"],
                body=data["body"],
                parent_message_id=data["parent_message_id"],
                data=data["data"],
            )
        ).model_dump(mode="json")
    )
