from __future__ import annotations

import base64
import hashlib
import hmac
import json
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import AppError
from app.db.models.project import Project
from app.db.models.project_member import ProjectMember
from app.db.models.runner import Runner
from app.db.models.task import Task
from app.db.models.task_event import TaskEvent
from app.db.models.user import User
from app.settings import DEFAULT_DEV_SECRET_KEY, get_settings


def read_identity_header(request: Request, header_name: str) -> str:
    """Read an X-*-Id style header that may be percent-encoded for non-ASCII transport.

    HTTP headers are latin-1 by spec, so clients with non-ASCII identifiers
    (e.g. 中文 workstation_id) percent-encode the value and set a sibling
    header `<Header>-Encoding: percent`. This helper transparently decodes both
    forms and returns the original utf-8 string."""
    raw = str(request.headers.get(header_name) or "").strip()
    if not raw:
        return ""
    encoding = str(request.headers.get(f"{header_name}-Encoding") or "").strip().lower()
    if encoding == "percent":
        try:
            return urllib.parse.unquote(raw)
        except Exception:
            return raw
    return raw


TOKEN_PREFIX = "ai-auth.v1"
DEFAULT_SESSION_TTL_SECONDS = 12 * 60 * 60


@dataclass(frozen=True)
class RequestPrincipal:
    actor_type: str
    actor_id: str
    auth_mode: str
    global_role: str = "member"
    user_id: str | None = None
    runner_id: str | None = None
    bootstrap: bool = False
    authenticated: bool = True


def _settings_secret() -> str:
    settings = get_settings()
    secret = settings.secret_key.strip()
    if not secret:
        if settings.is_production:
            raise AppError("SERVER_MISCONFIGURED", "server secret key is not configured", status_code=503)
        return DEFAULT_DEV_SECRET_KEY
    return secret


def _normalize_role(value: str | None) -> str:
    return (value or "member").strip().lower() or "member"


def _bearer_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "").strip()
    if not auth:
        return None
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        return token or None
    return None


def _encode_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_payload(encoded: str) -> dict[str, Any]:
    padded = encoded + "=" * (-len(encoded) % 4)
    raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    return json.loads(raw.decode("utf-8"))


def issue_access_token(user: User, *, ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS) -> tuple[str, datetime]:
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(seconds=max(60, ttl_seconds))
    payload = {
        "v": 1,
        "kind": "user",
        "sub": user.id,
        "role": _normalize_role(user.bio),
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    encoded = _encode_payload(payload)
    signature = hmac.new(_settings_secret().encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{TOKEN_PREFIX}.{encoded}.{signature}", expires_at


def verify_access_token(token: str) -> dict[str, Any] | None:
    parts = token.split(".")
    if len(parts) != 4 or parts[0] != "ai-auth" or parts[1] != "v1":
        return None
    encoded = parts[2]
    signature = parts[3]
    expected = hmac.new(_settings_secret().encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = _decode_payload(encoded)
    except Exception:
        return None
    if payload.get("v") != 1:
        return None
    exp = payload.get("exp")
    if not isinstance(exp, int):
        return None
    if datetime.now(timezone.utc).timestamp() > exp:
        return None
    return payload


def principal_to_dict(principal: RequestPrincipal) -> dict[str, Any]:
    return {
        "actor_type": principal.actor_type,
        "actor_id": principal.actor_id,
        "auth_mode": principal.auth_mode,
        "global_role": principal.global_role,
        "user_id": principal.user_id,
        "runner_id": principal.runner_id,
        "bootstrap": principal.bootstrap,
        "authenticated": True,
    }


def _user_to_principal(user: User, *, auth_mode: str, bootstrap: bool = False) -> RequestPrincipal:
    role = _normalize_role(user.bio)
    return RequestPrincipal(
        actor_type="human",
        actor_id=user.id,
        auth_mode=auth_mode,
        global_role=role,
        user_id=user.id,
        bootstrap=bootstrap,
    )


def _runner_to_principal(runner: Runner, *, auth_mode: str, bootstrap: bool = False) -> RequestPrincipal:
    return RequestPrincipal(
        actor_type="runner",
        actor_id=runner.id,
        auth_mode=auth_mode,
        global_role="runner",
        runner_id=runner.id,
        bootstrap=bootstrap,
    )


def _get_active_user(db: Session, user_id: str) -> User | None:
    stmt = select(User).where(User.id == user_id, User.is_active.is_(True))
    return db.scalar(stmt)


def _get_first_active_user(db: Session) -> User | None:
    stmt = select(User).where(User.is_active.is_(True)).order_by(User.created_at.asc())
    return db.scalar(stmt)


def _get_runner(db: Session, runner_id: str) -> Runner | None:
    return db.get(Runner, runner_id)


def _get_project_member(db: Session, project_id: str, user_id: str) -> ProjectMember | None:
    stmt = select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
    return db.scalar(stmt)


def _latest_runner_claim(db: Session, task_id: str) -> str | None:
    stmt = (
        select(TaskEvent)
        .where(TaskEvent.task_id == task_id, TaskEvent.event_type == "runner_picked")
        .order_by(TaskEvent.created_at.desc())
        .limit(1)
    )
    event = db.scalar(stmt)
    if event is None:
        return None
    return event.actor_id or (event.data or {}).get("runner_id")


def _project_role_is_privileged(role: str | None, member: ProjectMember | None = None) -> bool:
    if member is not None and member.is_owner:
        return True
    value = _normalize_role(role)
    markers = ("owner", "lead", "admin", "maintainer", "manager", "safety", "hardware", "runner", "arch")
    return any(marker in value for marker in markers)


def _platform_role_is_operator(role: str | None) -> bool:
    value = _normalize_role(role)
    markers = ("owner", "lead", "admin", "manager", "arch")
    return any(marker in value for marker in markers)


def require_platform_operator_principal(
    db: Session,
    request: Request,
    *,
    action: str = "platform.metadata.read",
) -> RequestPrincipal:
    principal = resolve_human_principal(db, request, allow_bootstrap=False)
    if _platform_role_is_operator(principal.global_role):
        return principal

    stmt = select(ProjectMember).where(
        ProjectMember.user_id == (principal.user_id or ""),
        ProjectMember.status == "active",
    )
    memberships = list(db.scalars(stmt))
    if any(_project_role_is_privileged(member.role, member) for member in memberships):
        return principal

    raise AppError(
        "PERMISSION_DENIED",
        f"missing permission for {action}",
        status_code=403,
        details={"action": action},
    )
    return principal


def resolve_human_principal(db: Session, request: Request, *, allow_bootstrap: bool = True) -> RequestPrincipal:
    token = _bearer_token(request)
    if token:
        claims = verify_access_token(token)
        if claims is None:
            raise AppError("UNAUTHORIZED", "无效的访问令牌", status_code=401)
        if claims.get("kind") != "user":
            raise AppError("UNAUTHORIZED", "该令牌不能用于人类写操作", status_code=401)
        user = _get_active_user(db, str(claims.get("sub") or ""))
        if user is None:
            raise AppError("UNAUTHORIZED", "用户不存在或已停用", status_code=401)
        return _user_to_principal(user, auth_mode="bearer")

    user_id = request.headers.get("x-user-id") or request.headers.get("x-actor-id")
    actor_type = (request.headers.get("x-actor-type") or "human").strip().lower()
    if user_id and actor_type in {"", "human", "user"}:
        user = _get_active_user(db, user_id)
        if user is None:
            raise AppError("UNAUTHORIZED", "用户不存在或已停用", status_code=401)
        return _user_to_principal(user, auth_mode="header")

    if allow_bootstrap and get_settings().allow_bootstrap_auth:
        user = _get_first_active_user(db)
        if user is not None:
            return _user_to_principal(user, auth_mode="bootstrap", bootstrap=True)

    raise AppError("UNAUTHORIZED", "authentication required", status_code=401)


def resolve_project_write_principal(
    db: Session,
    request: Request,
    project_id: str,
    *,
    require_privileged: bool = False,
    action: str = "project.write",
) -> RequestPrincipal:
    principal = resolve_human_principal(db, request)
    project = db.get(Project, project_id)
    if project is None:
        raise AppError("PROJECT_NOT_FOUND", "项目不存在", status_code=404)
    member = _get_project_member(db, project_id, principal.user_id or "")
    if member is None and not principal.bootstrap:
        raise AppError(
            "PERMISSION_DENIED",
            f"没有权限执行 {action}",
            status_code=403,
            details={"project_id": project_id, "action": action},
        )
    if require_privileged and not (principal.bootstrap or _project_role_is_privileged(principal.global_role, member)):
        raise AppError(
            "HUMAN_APPROVAL_REQUIRED",
            f"{action} 需要项目负责人或人工确认",
            status_code=403,
            details={"project_id": project_id, "action": action},
    )
    return principal


def resolve_project_write_principal_for_target(
    db: Session,
    request: Request,
    target: Any,
    *,
    require_privileged: bool = False,
    action: str = "project.write",
    project_id_attr: str = "project_id",
) -> RequestPrincipal:
    if isinstance(target, str):
        project_id = target.strip()
    elif isinstance(target, dict):
        project_id = str(target.get(project_id_attr) or "").strip()
    else:
        project_id = str(getattr(target, project_id_attr, "") or "").strip()
    if not project_id:
        raise AppError("PROJECT_NOT_FOUND", "椤圭洰涓嶅瓨鍦?", status_code=404)
    return resolve_project_write_principal(
        db,
        request,
        project_id,
        require_privileged=require_privileged,
        action=action,
    )


def resolve_task_write_principal(
    db: Session,
    request: Request,
    task_id: str,
    *,
    require_privileged: bool = False,
    action: str = "task.write",
) -> RequestPrincipal:
    task = db.get(Task, task_id)
    if task is None:
        raise AppError("TASK_NOT_FOUND", "未找到任务", status_code=404)
    return resolve_project_write_principal(
        db,
        request,
        task.project_id,
        require_privileged=require_privileged,
        action=action,
    )


def resolve_runner_principal(
    db: Session,
    request: Request,
    runner_id: str,
    *,
    action: str = "runner.write",
    allow_missing: bool = False,
) -> RequestPrincipal:
    settings = get_settings()
    runner = _get_runner(db, runner_id)

    token = _bearer_token(request)
    header_runner_id = read_identity_header(request, "x-runner-id")
    registration_token = request.headers.get("x-runner-registration-token", "").strip()
    if token:
        raise AppError("UNAUTHORIZED", "Runner written endpoints require x-runner-id", status_code=401)
    if runner is None:
        if not allow_missing and settings.app_env.lower() == "production":
            raise AppError("RUNNER_OFFLINE", "Runner 不存在或尚未注册", status_code=409)
        registration_token = request.headers.get("x-runner-registration-token", "").strip()
        configured_registration_token = settings.runner_registration_token.strip()
        if configured_registration_token:
            if not registration_token:
                raise AppError("UNAUTHORIZED", "Runner registration token is required", status_code=401)
            if registration_token != configured_registration_token:
                raise AppError("PERMISSION_DENIED", "Runner registration token is invalid", status_code=403)
        elif settings.app_env.lower() == "production":
            raise AppError("UNAUTHORIZED", "Production runner registration requires a pairing token", status_code=401)
        if not (token or header_runner_id or settings.app_env.lower() != "production"):
            raise AppError("UNAUTHORIZED", "Runner 写操作需要提供运行身份", status_code=401)
        return RequestPrincipal(
            actor_type="runner",
            actor_id=runner_id,
            auth_mode="bearer" if token else "header" if header_runner_id else "bootstrap",
            global_role="runner",
            runner_id=runner_id,
            bootstrap=settings.app_env.lower() != "production",
        )

    if token or header_runner_id:
        if header_runner_id and header_runner_id != runner_id:
            raise AppError(
                "PERMISSION_DENIED",
                f"{action} 的 runner_id 不匹配",
                status_code=403,
                details={"runner_id": runner_id, "header_runner_id": header_runner_id},
            )
        return _runner_to_principal(runner, auth_mode="bearer" if token else "header")

    if settings.app_env.lower() != "production":
        return _runner_to_principal(runner, auth_mode="bootstrap", bootstrap=True)

    raise AppError("UNAUTHORIZED", "Runner 写操作需要提供运行身份", status_code=401)


def resolve_runner_task_principal(
    db: Session,
    request: Request,
    task_id: str,
    *,
    require_claim: bool = True,
    action: str = "runner.task.write",
) -> RequestPrincipal:
    task = db.get(Task, task_id)
    if task is None:
        raise AppError("TASK_NOT_FOUND", "未找到任务", status_code=404)

    claimed_runner_id = _latest_runner_claim(db, task_id)
    token = _bearer_token(request)
    header_runner_id = read_identity_header(request, "x-runner-id")
    if token:
        raise AppError("UNAUTHORIZED", "Runner written endpoints require x-runner-id", status_code=401)

    if header_runner_id and claimed_runner_id and header_runner_id != claimed_runner_id:
        raise AppError(
            "TASK_CLAIMED_BY_OTHER_RUNNER",
            "该任务已经被其他执行节点领取",
            status_code=409,
            details={"task_id": task_id, "runner_id": header_runner_id, "claimed_runner_id": claimed_runner_id},
        )

    if header_runner_id:
        runner = _get_runner(db, header_runner_id)
        if runner is None:
            raise AppError("RUNNER_OFFLINE", "Runner 不存在或尚未注册", status_code=409)
        if claimed_runner_id and header_runner_id != claimed_runner_id:
            raise AppError(
                "TASK_CLAIMED_BY_OTHER_RUNNER",
                "该任务已经被其他执行节点领取",
                status_code=409,
                details={"task_id": task_id, "runner_id": header_runner_id, "claimed_runner_id": claimed_runner_id},
            )
        return _runner_to_principal(runner, auth_mode="header")

    if token:
        runner_id = claimed_runner_id
        if runner_id is None:
            if require_claim or get_settings().app_env.lower() == "production":
                raise AppError("TASK_NOT_CLAIMED", "任务还没有被任何执行节点领取", status_code=409)
            raise AppError("UNAUTHORIZED", "Runner 写操作需要可识别的执行节点", status_code=401)
        runner = _get_runner(db, runner_id)
        if runner is None:
            raise AppError("RUNNER_OFFLINE", "Runner 不存在或尚未注册", status_code=409)
        return _runner_to_principal(runner, auth_mode="bearer")

    if get_settings().app_env.lower() != "production" and claimed_runner_id:
        runner = _get_runner(db, claimed_runner_id)
        if runner is not None:
            return _runner_to_principal(runner, auth_mode="bootstrap", bootstrap=True)

    if require_claim:
        raise AppError("UNAUTHORIZED", f"{action} 需要 Runner 访问凭证", status_code=401)

    runner = _get_runner(db, claimed_runner_id) if claimed_runner_id else None
    if runner is None:
        raise AppError("UNAUTHORIZED", f"{action} 需要 Runner 访问凭证", status_code=401)
    return _runner_to_principal(runner, auth_mode="bootstrap", bootstrap=True)


def serialize_principal(principal: RequestPrincipal) -> dict[str, Any]:
    return principal_to_dict(principal)
