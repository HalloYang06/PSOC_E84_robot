from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=4, max_length=200)
    global_role: str = "member"


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=4, max_length=200)


class UserRead(BaseModel):
    id: str
    email: str
    name: str
    global_role: str = "member"
    is_active: bool = True
    notes: str | None = None
    display_name: str | None = None
    bio: str | None = None
    last_seen_at: datetime | None = None
    online_state: str | None = None
    online_label: str | None = None
    online_age_seconds: int | None = None
    online_fresh_seconds: int | None = None
    created_at: datetime | None
    updated_at: datetime | None

    class Config:
        from_attributes = True


class ProjectLiteRead(BaseModel):
    id: str
    name: str
    project_type: str | None = None
    default_branch: str | None = None
    develop_branch: str | None = None

    class Config:
        from_attributes = True


class InvitationCreate(BaseModel):
    email: str
    project_id: str | None = None
    role: str = "collaborator"
    invited_by_user_id: str | None = None
    note: str | None = None


class InvitationAcceptRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    password: str | None = Field(default=None, min_length=4, max_length=200)
    accepted_by_user_id: str | None = None


class InvitationRead(BaseModel):
    id: str
    email: str
    project_id: str | None
    role: str
    invited_by_user_id: str | None
    status: str
    note: str | None
    accepted_by_user_id: str | None
    accepted_at: datetime | None
    created_at: datetime | None
    project: ProjectLiteRead | None = None
    invited_by_user: UserRead | None = None
    accepted_by_user: UserRead | None = None

    class Config:
        from_attributes = True


class ProjectMemberRead(BaseModel):
    id: str
    project_id: str
    user_id: str
    role: str
    status: str | None = None
    is_owner: bool = False
    last_project_seen_at: datetime | None = None
    last_project_path: str | None = None
    project_presence_state: str | None = None
    project_presence_label: str | None = None
    project_presence_age_seconds: int | None = None
    project_presence_fresh_seconds: int | None = None
    joined_at: datetime | None = None
    created_at: datetime | None
    updated_at: datetime | None = None
    project: ProjectLiteRead | None = None
    user: UserRead | None = None

    class Config:
        from_attributes = True


class AuthSummaryRead(BaseModel):
    users: int
    pending_invitations: int
    accepted_invitations: int
    project_members: int


class WorkspaceProjectRead(BaseModel):
    project_id: str
    project_name: str
    project_type: str | None = None
    default_branch: str | None = None
    develop_branch: str | None = None
    description: str | None = None
    role: str
    is_owner: bool = False
    joined_at: datetime | None = None
    pending_human_review_count: int = 0
    pending_human_review_title: str | None = None
    pending_human_review_detail: str | None = None
    pending_human_review_level: str | None = None


class AuthWorkspaceRead(BaseModel):
    user: UserRead
    projects: list[WorkspaceProjectRead]
    pending_invitations: list[InvitationRead]


class RequestPrincipalRead(BaseModel):
    actor_type: str
    actor_id: str
    auth_mode: str
    global_role: str = "member"
    user_id: str | None = None
    runner_id: str | None = None
    bootstrap: bool = False
    authenticated: bool = True


class AuthSessionRead(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime | None = None
    user: UserRead
    principal: RequestPrincipalRead
