from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.common.access import (
    issue_access_token,
    require_platform_operator_principal,
    resolve_human_principal,
    serialize_principal,
)
from app.common.access import resolve_project_write_principal
from app.common.errors import AppError
from app.common.response import ok
from app.db.models.invitation import Invitation
from app.db.models.user import User
from app.db.session import get_db

from .schemas import (
    AuthWorkspaceRead,
    AuthSessionRead,
    AuthSummaryRead,
    InvitationAcceptRequest,
    InvitationCreate,
    InvitationRead,
    LoginRequest,
    RequestPrincipalRead,
    WorkspaceProjectRead,
    ProjectMemberRead,
    RegisterRequest,
    UserRead,
)
from .service import (
    accept_invitation,
    create_invitation,
    get_auth_summary,
    list_user_pending_invitations,
    list_user_workspace_projects,
    list_invitations,
    list_project_members,
    list_users,
    login_user,
    register_user,
    serialize_invitation_for_read,
    serialize_member_for_read,
    serialize_user_for_read,
)


router = APIRouter(prefix="/api/auth", tags=["auth"])


def _require_real_human_principal(db: Session, request: Request):
    principal = resolve_human_principal(db, request, allow_bootstrap=False)
    if not principal.authenticated:
        raise AppError("UNAUTHORIZED", "authentication required", status_code=401)
    return principal


@router.post("/register")
def api_register(payload: RegisterRequest, db: Session = Depends(get_db)):
    return ok(UserRead.model_validate(serialize_user_for_read(register_user(db, payload))).model_dump(mode="json"))


@router.post("/login")
def api_login(payload: LoginRequest, db: Session = Depends(get_db)):
    return ok(UserRead.model_validate(serialize_user_for_read(login_user(db, payload))).model_dump(mode="json"))


@router.post("/session")
def api_session(payload: LoginRequest, db: Session = Depends(get_db)):
    user = login_user(db, payload)
    token, expires_at = issue_access_token(user)
    principal = RequestPrincipalRead.model_validate(
        {
            "actor_type": "human",
            "actor_id": user.id,
            "auth_mode": "session",
            "global_role": (user.bio or "member").strip().lower() or "member",
            "user_id": user.id,
            "runner_id": None,
            "bootstrap": False,
            "authenticated": True,
        }
    )
    return ok(
        AuthSessionRead(
            access_token=token,
            expires_at=expires_at,
            user=UserRead.model_validate(serialize_user_for_read(user)),
            principal=principal,
        ).model_dump(mode="json")
    )


@router.get("/me")
def api_me(request: Request, db: Session = Depends(get_db)):
    principal = RequestPrincipalRead.model_validate(serialize_principal(resolve_human_principal(db, request)))
    user = db.get(User, principal.user_id) if principal.user_id is not None else None
    return ok(
        {
            "principal": principal.model_dump(mode="json"),
            "user": UserRead.model_validate(serialize_user_for_read(user)).model_dump(mode="json") if user else None,
        }
    )


@router.get("/workspace")
def api_workspace(request: Request, db: Session = Depends(get_db)):
    principal = _require_real_human_principal(db, request)
    user = db.get(User, principal.user_id) if principal.user_id is not None else None
    if user is None:
        raise AppError("UNAUTHORIZED", "authentication required", status_code=401)
    return ok(
        AuthWorkspaceRead(
            user=UserRead.model_validate(serialize_user_for_read(user)),
            projects=[WorkspaceProjectRead.model_validate(item) for item in list_user_workspace_projects(db, user.id)],
            pending_invitations=[InvitationRead.model_validate(item) for item in list_user_pending_invitations(db, user.email)],
        ).model_dump(mode="json")
    )


@router.get("/users")
def api_users(request: Request, db: Session = Depends(get_db)):
    require_platform_operator_principal(db, request, action="auth.users.read")
    return ok([UserRead.model_validate(serialize_user_for_read(item)).model_dump(mode="json") for item in list_users(db)])


@router.get("/invitations")
def api_invitations(request: Request, project_id: str | None = None, status: str | None = None, db: Session = Depends(get_db)):
    if project_id:
        resolve_project_write_principal(db, request, project_id, action="auth.invitation.read")
    else:
        require_platform_operator_principal(db, request, action="auth.invitations.read")
    return ok([InvitationRead.model_validate(item).model_dump(mode="json") for item in list_invitations(db, project_id=project_id, status=status)])


@router.get("/summary")
def api_summary(request: Request, db: Session = Depends(get_db)):
    require_platform_operator_principal(db, request, action="auth.summary.read")
    return ok(AuthSummaryRead.model_validate(get_auth_summary(db)).model_dump(mode="json"))


@router.post("/invitations")
def api_create_invitation(payload: InvitationCreate, request: Request, db: Session = Depends(get_db)):
    if not payload.project_id:
        raise AppError("VALIDATION_ERROR", "project_id is required", status_code=422)
    principal = _require_real_human_principal(db, request)
    resolve_project_write_principal(db, request, payload.project_id, require_privileged=True, action="auth.invitation.create")
    item = create_invitation(db, payload.model_copy(update={"invited_by_user_id": principal.user_id}))
    return ok(InvitationRead.model_validate(serialize_invitation_for_read(item)).model_dump(mode="json"))


@router.post("/invitations/{invitation_id}/accept")
def api_accept_invitation(invitation_id: str, payload: InvitationAcceptRequest, request: Request, db: Session = Depends(get_db)):
    principal = _require_real_human_principal(db, request)
    invitation = db.get(Invitation, invitation_id)
    if invitation is None:
        raise AppError("INVITATION_NOT_FOUND", "invitation not found", status_code=404)
    current_user = db.get(User, principal.user_id) if principal.user_id else None
    if invitation.email and current_user is not None and current_user.email != invitation.email:
        raise AppError("INVITATION_EMAIL_MISMATCH", "current identity does not match invitation email", status_code=403)
    result = accept_invitation(
        db,
        invitation_id,
        payload.model_copy(update={"accepted_by_user_id": principal.user_id}),
    )
    return ok(
        {
            "invitation": InvitationRead.model_validate(serialize_invitation_for_read(result["invitation"])).model_dump(mode="json"),
            "user": UserRead.model_validate(serialize_user_for_read(result["user"])).model_dump(mode="json"),
        }
    )


@router.get("/projects/{project_id}/members")
def api_project_members(project_id: str, request: Request, db: Session = Depends(get_db)):
    resolve_project_write_principal(db, request, project_id, action="auth.project_members.read")
    return ok([ProjectMemberRead.model_validate(item).model_dump(mode="json") for item in list_project_members(db, project_id)])


@router.get("/projects/{project_id}/invitations")
def api_project_invitations(project_id: str, request: Request, status: str | None = None, db: Session = Depends(get_db)):
    resolve_project_write_principal(db, request, project_id, action="auth.project_invitations.read")
    items = list_invitations(db, project_id=project_id, status=status)
    return ok([InvitationRead.model_validate(item).model_dump(mode="json") for item in items])
