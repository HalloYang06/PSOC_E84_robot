from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.common.response import ok
from app.common.response import ok_paginated
from app.db.session import get_db
from app.modules.read_access import (
    readable_project_ids,
    require_project_read_access,
    require_real_human_principal,
)
from app.modules.auth.schemas import InvitationCreate, InvitationRead, ProjectMemberRead
from app.modules.auth.service import (
    create_invitation,
    list_invitations as list_project_invites,
    list_project_members as list_project_members_auth,
    mark_project_presence,
    serialize_invitation_for_read,
    serialize_member_for_read,
)
from app.modules.collaboration.schemas import ProjectMemberCreate
from app.modules.messages.schemas import MessageCreate, MessageRead
from app.modules.messages.service import create_entity_message, list_entity_messages

from .schemas import (
    ProjectConfigRead,
    ProjectConfigUpdate,
    ProjectCreate,
    ProjectPresencePing,
    ProjectRead,
    ProjectRollbackRequest,
    ProjectSyncRequest,
    ProjectUpdate,
)
from .service import (
    add_project_member_to_project,
    create_project,
    get_project_or_404,
    list_projects,
    rollback_project,
    sync_project_github,
    get_project_config,
    serialize_project_for_read,
    update_project_config,
    update_project,
)


router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
def api_list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    request: Request = None,
    db: Session = Depends(get_db),
):
    readable_ids = set(readable_project_ids(db, request))
    items = [item for item in list_projects(db) if str(item.id) in readable_ids]
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    rows = [ProjectRead.model_validate(serialize_project_for_read(item)).model_dump(mode="json") for item in items[start:end]]
    return ok_paginated(rows, page=page, page_size=page_size, total=total)


@router.post("")
def api_create_project(payload: ProjectCreate, request: Request, db: Session = Depends(get_db)):
    principal = require_real_human_principal(db, request)
    return ok(
        ProjectRead.model_validate(
            serialize_project_for_read(create_project(db, payload, owner_user_id=principal.user_id))
        ).model_dump(mode="json")
    )


@router.get("/{project_id}")
def api_get_project(project_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="project.read")
    return ok(ProjectRead.model_validate(serialize_project_for_read(get_project_or_404(db, project_id))).model_dump(mode="json"))


@router.patch("/{project_id}")
def api_update_project(project_id: str, payload: ProjectUpdate, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="project.update")
    from app.common.access import resolve_project_write_principal

    resolve_project_write_principal(db, request, project_id, action="project.update")
    return ok(ProjectRead.model_validate(serialize_project_for_read(update_project(db, project_id, payload))).model_dump(mode="json"))


@router.get("/{project_id}/config")
def api_get_project_config(project_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="project.config.read")
    return ok(ProjectConfigRead.model_validate(get_project_config(db, project_id)).model_dump(mode="json"))


@router.patch("/{project_id}/config")
def api_update_project_config(project_id: str, payload: ProjectConfigUpdate, request: Request, db: Session = Depends(get_db)):
    from app.common.access import resolve_project_write_principal

    resolve_project_write_principal(db, request, project_id, require_privileged=True, action="project.config.update")
    return ok(ProjectConfigRead.model_validate(update_project_config(db, project_id, payload)).model_dump(mode="json"))


@router.post("/{project_id}/sync-github")
def api_sync_project_github(project_id: str, payload: ProjectSyncRequest, request: Request, db: Session = Depends(get_db)):
    from app.common.access import resolve_project_write_principal

    resolve_project_write_principal(db, request, project_id, require_privileged=True, action="project.sync_github")
    return ok(sync_project_github(db, project_id, payload))


@router.post("/{project_id}/rollback")
def api_rollback_project(project_id: str, payload: ProjectRollbackRequest, request: Request, db: Session = Depends(get_db)):
    from app.common.access import resolve_project_write_principal

    resolve_project_write_principal(db, request, project_id, require_privileged=True, action="project.rollback")
    return ok(rollback_project(db, project_id, payload))


@router.get("/{project_id}/members")
def api_project_members(project_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="project.members.read")
    return ok(list_project_members_auth(db, project_id))


@router.post("/{project_id}/presence")
def api_project_presence(project_id: str, payload: ProjectPresencePing, request: Request, db: Session = Depends(get_db)):
    principal = require_project_read_access(db, request, project_id, action="project.presence")
    item = mark_project_presence(db, project_id, principal.user_id or "", path=payload.path)
    return ok(ProjectMemberRead.model_validate(item).model_dump(mode="json"))


@router.get("/{project_id}/invitations")
def api_project_invitations(project_id: str, status: str | None = None, request: Request = None, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="project.invitations.read")
    return ok(list_project_invites(db, project_id=project_id, status=status))


@router.post("/{project_id}/invitations")
def api_create_project_invitation(project_id: str, payload: InvitationCreate, request: Request, db: Session = Depends(get_db)):
    from app.common.access import resolve_project_write_principal

    resolve_project_write_principal(db, request, project_id, require_privileged=True, action="project.invitation.create")
    item = create_invitation(db, payload.model_copy(update={"project_id": project_id}))
    return ok(InvitationRead.model_validate(serialize_invitation_for_read(item)).model_dump(mode="json"))


@router.post("/{project_id}/members")
def api_create_project_member(project_id: str, payload: ProjectMemberCreate, request: Request, db: Session = Depends(get_db)):
    from app.common.access import resolve_project_write_principal

    principal = require_real_human_principal(db, request)
    existing_members = list_project_members_auth(db, project_id)
    if not (not existing_members and payload.is_owner and principal.user_id == payload.user_id):
        resolve_project_write_principal(db, request, project_id, require_privileged=True, action="project.member.create")
    item = add_project_member_to_project(
        db,
        project_id,
        user_id=payload.user_id,
        role=payload.role,
        status=payload.status,
        is_owner=payload.is_owner,
    )
    return ok(ProjectMemberRead.model_validate(serialize_member_for_read(item)).model_dump(mode="json"))


@router.get("/{project_id}/messages")
def api_project_messages(project_id: str, message_type: str | None = None, request: Request = None, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="project.messages.read")
    items = list_entity_messages(db, "project", project_id, project_id=project_id, message_type=message_type)
    return ok([MessageRead.model_validate(item).model_dump(mode="json") for item in items])


@router.post("/{project_id}/messages")
def api_create_project_message(project_id: str, payload: MessageCreate, request: Request, db: Session = Depends(get_db)):
    from app.common.access import resolve_project_write_principal

    resolve_project_write_principal(db, request, project_id, action="project.message.create")
    data = payload.model_dump()
    data["project_id"] = project_id
    data["entity_type"] = "project"
    data["entity_id"] = project_id
    return ok(MessageRead.model_validate(create_entity_message(db, "project", project_id, project_id=project_id, message_type=data["message_type"], sender_type=data["sender_type"], sender_id=data["sender_id"], body=data["body"], parent_message_id=data["parent_message_id"], data=data["data"])).model_dump(mode="json"))
