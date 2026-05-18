from __future__ import annotations

import hashlib
import hmac
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.common.access import read_identity_header, resolve_human_principal, resolve_project_write_principal
from app.common.errors import AppError
from app.common.response import ok
from app.db.models.collaboration_message import CollaborationMessage
from app.db.session import get_db
from app.db.models.approval import Approval
from app.db.models.project import Project
from app.db.models.project_collaboration import ProjectComputerNode, ProjectThreadWorkstation, ProjectWorkstation
from app.db.models.task import Task
from app.db.models.user import User
from app.modules.audit.service import create_audit_log
from app.settings import get_settings
from app.modules.projects.schemas import (
    CollaborationComputerNodeRead,
    CollaborationProviderRead,
    CollaborationWorkstationRead,
    ProjectConfigRead,
)
from app.modules.handoffs.service import get_handoff_or_404
from app.modules.messages.service import create_entity_message
from app.modules.requirements.service import get_requirement_or_404
from app.modules.requirements.schemas import RequirementRead, StructuredNeedCreate
from app.modules.requirements.service import create_structured_need
from app.modules.seats.service import get_seat_queues
from app.modules.read_access import (
    readable_project_ids,
    require_project_read_access,
    resolve_approval_project_id,
    resolve_handoff_project_id,
    resolve_requirement_project_id,
    resolve_task_project_id,
)

from .schemas import (
    CollaborationMessageCreate,
    CollaborationMessagePreviewRead,
    CollaborationMessageRead,
    CollaborationMessageUpdate,
    ComputerNodePairingTokenRead,
    DesktopCloseoutActionCreate,
    RunnerRelayAckCreate,
    RunnerRelayCommandCreate,
    RunnerRelayCompleteCreate,
    WorkstationInboxAckCreate,
    DesktopThreadSyncCreate,
    WorkstationInboxProgressCreate,
    WorkstationAdapterConfigRead,
    WorkstationAdapterTokenRead,
    WorkstationInboxCompleteCreate,
    RunnerRelayMessageRead,
    CollaborationComputerNodeCreate,
    CollaborationComputerNodeUpdate,
    CollaborationConfigUpdate,
    CollaborationProviderCreate,
    CollaborationProviderUpdate,
    CollaborationWorkstationCreate,
    CollaborationWorkstationUpdate,
    CollaborationSummaryRead,
    ProjectInviteAcceptRequest,
    ProjectInviteCreate,
    ProjectInviteRead,
    ProjectInviteUpdate,
    ProjectMemberCreate,
    ProjectMemberRead,
    ProjectMemberUpdate,
    UserCreate,
    UserRead,
    UserUpdate,
)
from .service import (
    accept_invite,
    ack_runner_command,
    add_project_member,
    complete_runner_command,
    create_project_invite,
    create_user,
    create_runner_command,
    ack_workstation_command,
    complete_workstation_command,
    closeout_workstation_command,
    progress_workstation_command,
    get_collaboration_summary,
    get_collaboration_message_or_404,
    get_project_ai_provider,
    get_project_collaboration_config,
    get_project_computer_node_pairing_status,
    get_project_computer_node,
    get_project_workstation_adapter_token_status,
    get_project_workstation_adapter_config,
    get_project_thread_workstation,
    get_invite_or_404,
    get_user_or_404,
    list_messages,
    list_project_ai_providers,
    list_project_computer_nodes,
    list_project_invites,
    list_project_members,
    list_project_thread_workstations,
    list_users,
    list_runner_inbox_messages,
    list_workstation_inbox_messages,
    mark_project_workstation_adapter_token_used,
    create_message as create_collaboration_message,
    create_project_ai_provider,
    create_project_computer_node,
    create_project_thread_workstation,
    delete_project_ai_provider,
    delete_project_computer_node,
    delete_project_thread_workstation,
    remove_project_member,
    revoke_project_computer_node_pairing_token,
    revoke_project_workstation_adapter_token,
    revoke_invite,
    rotate_project_computer_node_pairing_token,
    rotate_project_workstation_adapter_token,
    serialize_project_invite_for_read,
    update_project_ai_provider,
    update_collaboration_message,
    update_project_collaboration_config,
    update_project_computer_node,
    update_project_thread_workstation,
    update_project_invite,
    update_project_member,
    update_user,
    autostart_workstation_command_after_review,
)


router = APIRouter(prefix="/api/collaboration", tags=["collaboration"])


HARDWARE_REVIEW_KEYWORDS = (
    "上电",
    "断电",
    "实机",
    "真机",
    "机械臂",
    "电机",
    "舵机",
    "急停",
    "刷写",
    "固件",
    "烧录",
    "电源",
    "电压",
    "电流",
    "电池",
    "夹爪",
    "ros",
    "vla",
    "moveit",
    "gpio",
    "motor",
    "servo",
    "firmware",
    "flash",
    "power on",
    "emergency stop",
    "hardware",
    "robot",
    "robotic arm",
)


READONLY_FRONTEND_REVIEW_EXEMPT_MARKERS = (
    "只读前端",
    "只读工作面",
    "只读能力",
    "只读入口",
    "只读证据",
    "只读诊断",
    "只读规划",
    "只读观测",
    "桌面同步",
    "执行线程恢复",
    "恢复验证",
    "抗干扰",
    "建议卡",
    "调参建议",
    "强审动作卡",
    "不得自动执行",
    "不得执行",
    "不能自动执行",
    "不自动执行",
    "截图验收",
    "浏览器验收",
    "点击链验收",
    "全链路验收",
    "fullchain",
    "复验",
    "结构契约",
    "工作台结构",
    "dom 检查",
    "dom检查",
    "页面验收",
    "前端验收",
    "只跑验证",
    "不改硬件",
    "不要碰真实硬件",
    "不碰真实硬件",
    "不执行 ros",
    "不执行ros",
    "不写操作",
    "不要写操作",
    "不部署",
    "不运动",
    "前端能力",
    "read-only frontend",
    "readonly frontend",
    "screenshot validation",
    "dom check",
    "cdp",
    "browser validation",
    "click-chain validation",
    "fullchain validation",
)

HARDWARE_ACTION_MARKERS = (
    "上电",
    "断电",
    "实机",
    "真机",
    "刷写",
    "固件",
    "烧录",
    "写参数",
    "下发",
    "运动",
    "移动",
    "急停",
    "部署",
    "publish",
    "service",
    "action",
    "write parameter",
    "firmware",
    "flash",
    "power on",
    "motion",
    "deploy",
)

HARDWARE_GUARDRAIL_MARKERS = (
    "必须单独做强审",
    "必须强审",
    "必须走强审",
    "强制人审",
    "不得自动执行",
    "不能自动执行",
    "不自动执行",
    "不要碰",
    "不碰真实硬件",
    "不执行",
    "不部署",
    "不运动",
    "不写",
    "不能直接下发",
    "不能下发",
    "只能生成建议",
    "只展示",
    "只读",
)


def _detect_hardware_review_risk(text: str) -> str | None:
    cleaned = str(text or "").strip().lower()
    if not cleaned:
        return None
    has_readonly_exempt_marker = any(marker.lower() in cleaned for marker in READONLY_FRONTEND_REVIEW_EXEMPT_MARKERS)
    has_guardrail_marker = any(marker.lower() in cleaned for marker in HARDWARE_GUARDRAIL_MARKERS)
    if any(marker.lower() in cleaned for marker in READONLY_FRONTEND_REVIEW_EXEMPT_MARKERS) and not any(
        marker.lower() in cleaned for marker in HARDWARE_ACTION_MARKERS
    ):
        return None
    if has_readonly_exempt_marker and has_guardrail_marker:
        return None
    for keyword in HARDWARE_REVIEW_KEYWORDS:
        if keyword.lower() in cleaned:
            return keyword
    risky_motion = re.search(r"(启动|运行|移动|校准|测试|执行|下发|控制).{0,16}(机械臂|电机|舵机|夹爪|实机|真机)", cleaned)
    if risky_motion is not None:
        return risky_motion.group(0)
    return None


def _require_real_human_principal(db: Session, request: Request):
    return resolve_human_principal(db, request, allow_bootstrap=False)


def _invite_project_id(db: Session, invite_id: str) -> str:
    invite = get_invite_or_404(db, invite_id)
    if invite.project_id:
        return invite.project_id
    raise AppError("PROJECT_NOT_FOUND", "invite has no project context", status_code=404)


def _computer_node_owner_user_id(node: dict[str, object] | None) -> str:
    if not isinstance(node, dict):
        return ""
    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    return str(metadata.get("owner_user_id") or metadata.get("created_by_user_id") or "").strip()


def _resolve_computer_node_manager_principal(
    db: Session,
    request: Request,
    *,
    project_id: str,
    node_id: str,
    action: str,
):
    principal = _require_real_human_principal(db, request)
    try:
        resolve_project_write_principal(
            db,
            request,
            project_id,
            require_privileged=True,
            action=action,
        )
        return principal
    except AppError as error:
        if error.code != "HUMAN_APPROVAL_REQUIRED":
            raise

    resolve_project_write_principal(db, request, project_id, action=action)
    node = get_project_computer_node(db, project_id, node_id)
    owner_user_id = _computer_node_owner_user_id(node)
    if owner_user_id and principal.user_id and owner_user_id == principal.user_id:
        return principal
    raise AppError(
        "HUMAN_APPROVAL_REQUIRED",
        f"{action} 需要这台电脑的接入人或项目负责人",
        status_code=403,
        details={"project_id": project_id, "computer_node_id": node_id, "owner_user_id": owner_user_id or None},
    )


def _workstation_computer_node_id(workstation: dict[str, object] | None) -> str:
    if not isinstance(workstation, dict):
        return ""
    metadata = workstation.get("metadata") if isinstance(workstation.get("metadata"), dict) else {}
    return str(
        workstation.get("computer_node_id")
        or workstation.get("computer_node")
        or metadata.get("computer_node_id")
        or metadata.get("computer_node")
        or ""
    ).strip()


def _resolve_workstation_manager_principal(
    db: Session,
    request: Request,
    *,
    project_id: str,
    computer_node_id: str | None,
    action: str,
):
    principal = _require_real_human_principal(db, request)
    try:
        resolve_project_write_principal(
            db,
            request,
            project_id,
            require_privileged=True,
            action=action,
        )
        return principal
    except AppError as error:
        if error.code != "HUMAN_APPROVAL_REQUIRED":
            raise

    resolve_project_write_principal(db, request, project_id, action=action)
    node_id = str(computer_node_id or "").strip()
    if node_id:
        node = get_project_computer_node(db, project_id, node_id)
        owner_user_id = _computer_node_owner_user_id(node)
        if owner_user_id and principal.user_id and owner_user_id == principal.user_id:
            return principal
    raise AppError(
        "HUMAN_APPROVAL_REQUIRED",
        f"{action} 需要这台电脑的接入人或项目负责人",
        status_code=403,
        details={"project_id": project_id, "computer_node_id": node_id or None},
    )


def _collaboration_message_project_id(db: Session, payload: CollaborationMessageCreate) -> str:
    if payload.project_id:
        return payload.project_id
    if payload.task_id:
        task = db.get(Task, payload.task_id)
        if task is not None and task.project_id:
            return task.project_id
    if payload.approval_id:
        approval = db.get(Approval, payload.approval_id)
        if approval is not None and approval.project_id:
            return approval.project_id
    if payload.requirement_id:
        requirement = get_requirement_or_404(db, payload.requirement_id)
        if requirement.project_id:
            return requirement.project_id
        if requirement.task_id:
            task = db.get(Task, requirement.task_id)
            if task is not None and task.project_id:
                return task.project_id
    if payload.handoff_id:
        handoff = get_handoff_or_404(db, payload.handoff_id)
        if handoff.project_id:
            return handoff.project_id
        if handoff.task_id:
            task = db.get(Task, handoff.task_id)
            if task is not None and task.project_id:
                return task.project_id
    raise AppError("PROJECT_NOT_FOUND", "collaboration message requires a project context", status_code=404)


def _build_collaboration_message_preview_signature(
    payload: CollaborationMessageCreate,
    *,
    project_id: str,
    sender_id: str | None,
) -> str:
    normalized = {
        "project_id": project_id,
        "task_id": payload.task_id,
        "approval_id": payload.approval_id,
        "handoff_id": payload.handoff_id,
        "requirement_id": payload.requirement_id,
        "agent_id": payload.agent_id,
        "message_type": str(payload.message_type or "comment_message").strip() or "comment_message",
        "title": (str(payload.title or "").strip() or None),
        "body": str(payload.body or "").strip(),
        "sender_type": "human",
        "sender_id": (str(sender_id or "").strip() or None),
        "recipient_type": (str(payload.recipient_type or "").strip() or None),
        "recipient_id": (str(payload.recipient_id or "").strip() or None),
        "status": str(payload.status or "open").strip() or "open",
    }
    return hashlib.sha256(json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]


def _collaboration_payload_extra_data(payload: CollaborationMessageCreate) -> dict[str, object]:
    return dict(payload.metadata or {}) if isinstance(payload.metadata, dict) else {}


def _payload_card_kind(metadata: dict[str, object]) -> str:
    payload = metadata.get("payload_json") or metadata.get("payloadJson")
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            parsed = {}
        payload = parsed
    if not isinstance(payload, dict):
        payload = {}
    raw = payload.get("card_kind") or payload.get("cardKind") or payload.get("kind") or metadata.get("card_kind") or metadata.get("cardKind")
    return str(raw or "").strip().lower().replace("_", "-")


def _payload_risk_level(metadata: dict[str, object]) -> str:
    payload = metadata.get("payload_json") or metadata.get("payloadJson")
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            parsed = {}
        payload = parsed
    if isinstance(payload, dict):
        raw = payload.get("risk_level") or payload.get("riskLevel")
        if raw:
            return str(raw).strip() or "L1"
    raw = metadata.get("risk_level") or metadata.get("riskLevel")
    return str(raw or "L1").strip() or "L1"


def _ensure_peer_delegation_context(
    metadata: dict[str, object],
    *,
    project_id: str,
    delegated_by_user_id: str | None,
    delegated_via_seat_id: str,
    target_seat_id: str,
    source_message_id: str | None,
) -> dict[str, object]:
    now = datetime.now(UTC)
    existing = metadata.get("delegation_context")
    if isinstance(existing, dict) and existing.get("kind") == "project_delegation":
        context = dict(existing)
    else:
        context = {
            "kind": "project_delegation",
            "version": 1,
            "project_id": project_id,
            "delegated_by_user_id": delegated_by_user_id,
            "delegated_via_seat_id": delegated_via_seat_id,
            "grantee_type": "seat",
            "grantee_id": delegated_via_seat_id,
            "target_seat_id": target_seat_id,
            "scope": [
                "collaboration.message.create",
                "collaboration.peer_dispatch.create",
                "collaboration.receipt.write",
            ],
            "max_risk_level": _payload_risk_level(metadata),
            "source_message_id": source_message_id,
            "source": str(metadata.get("origin") or metadata.get("source") or "agent_peer_dispatch"),
            "issued_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=12)).isoformat(),
            "revoked_at": None,
            "status": "active",
        }
    metadata["delegation_context"] = context
    metadata.setdefault("delegated_by_user_id", context.get("delegated_by_user_id"))
    metadata.setdefault("delegated_via_seat_id", context.get("delegated_via_seat_id"))
    metadata.setdefault("delegation_scope", context.get("scope"))
    metadata.setdefault("delegation_status", context.get("status"))
    return metadata


def _resolve_delegated_by_user_id_for_peer_dispatch(
    db: Session,
    *,
    project_id: str,
    source_message_id: str | None,
    fallback_user_id: str | None,
) -> str | None:
    cleaned_fallback = str(fallback_user_id or "").strip() or None
    if cleaned_fallback:
        return cleaned_fallback
    cleaned_source = str(source_message_id or "").strip()
    visited: set[str] = set()
    while cleaned_source and cleaned_source not in visited:
        visited.add(cleaned_source)
        source = db.get(CollaborationMessage, cleaned_source)
        if source is None or source.project_id != project_id:
            return None
        if (source.sender_type or "").lower() == "human" and source.sender_id:
            return str(source.sender_id)
        extra = source.extra_data if isinstance(source.extra_data, dict) else {}
        delegated_by = str(extra.get("delegated_by_user_id") or "").strip()
        if delegated_by:
            return delegated_by
        context = extra.get("delegation_context")
        if isinstance(context, dict):
            context_user = str(context.get("delegated_by_user_id") or "").strip()
            if context_user:
                return context_user
            next_source = str(context.get("source_message_id") or "").strip()
            if next_source and next_source != cleaned_source:
                cleaned_source = next_source
                continue
        next_source = str(extra.get("source_message_id") or extra.get("root_message_id") or "").strip()
        if next_source and next_source != cleaned_source:
            cleaned_source = next_source
            continue
        return None
    return None


def _resolve_collaboration_message_recipient_label(
    db: Session,
    *,
    project_id: str,
    recipient_type: str | None,
    recipient_id: str | None,
) -> tuple[str | None, bool]:
    cleaned_type = str(recipient_type or "").strip().lower()
    cleaned_id = str(recipient_id or "").strip()
    if not cleaned_type or not cleaned_id:
        return None, False
    if cleaned_type == "workstation":
        workstation = _project_workstation_by_id_or_config(db, project_id, cleaned_id)
        if workstation is None:
            from app.modules.requirements.service import _resolve_seat

            seat = _resolve_seat(db, project_id, cleaned_id)
            if seat is None:
                raise AppError(
                    "NOT_FOUND",
                    "thread workstation does not exist",
                    status_code=404,
                )
            label = str(seat.name or seat.id or seat.config_id or cleaned_id).strip() or cleaned_id
            return label, True
        label = str(workstation.name or workstation.id or workstation.config_id or cleaned_id).strip() or cleaned_id
        return label, True
    if cleaned_type == "computer_node":
        node = get_project_computer_node(db, project_id, cleaned_id)
        if isinstance(node, dict):
            label = str(node.get("label") or node.get("id") or node.get("node_id") or cleaned_id).strip() or cleaned_id
        else:
            label = str(node.label or node.id or cleaned_id).strip() or cleaned_id
        return label, True
    return cleaned_id, True


def _collaboration_message_scope_project_id(
    db: Session,
    *,
    project_id: str | None = None,
    task_id: str | None = None,
    approval_id: str | None = None,
    handoff_id: str | None = None,
    requirement_id: str | None = None,
    agent_id: str | None = None,
) -> str:
    if project_id:
        return project_id
    if task_id:
        return resolve_task_project_id(db, task_id)
    if approval_id:
        return resolve_approval_project_id(db, approval_id)
    if handoff_id:
        return resolve_handoff_project_id(db, handoff_id)
    if requirement_id:
        return resolve_requirement_project_id(db, requirement_id)
    cleaned_agent_id = str(agent_id or "").strip()
    if cleaned_agent_id:
        candidate_ids = {
            str(item or "").strip()
            for item in db.scalars(
                select(ProjectThreadWorkstation.project_id).where(
                    or_(
                        ProjectThreadWorkstation.id == cleaned_agent_id,
                        ProjectThreadWorkstation.config_id == cleaned_agent_id,
                    )
                )
            )
            if str(item or "").strip()
        }
        candidate_ids.update(
            {
                str(item or "").strip()
                for item in db.scalars(
                    select(CollaborationMessage.project_id).where(CollaborationMessage.agent_id == cleaned_agent_id)
                )
                if str(item or "").strip()
            }
        )
        if len(candidate_ids) == 1:
            return next(iter(candidate_ids))
        if len(candidate_ids) > 1:
            raise AppError(
                "VALIDATION_ERROR",
                "collaboration message read requires project_id when agent_id spans multiple projects",
                status_code=422,
            )
    raise AppError("VALIDATION_ERROR", "collaboration message read requires a project context", status_code=422)


def _workstation_identity_values(workstation_id: str, workstation: dict[str, object]) -> set[str]:
    metadata = workstation.get("metadata") if isinstance(workstation.get("metadata"), dict) else {}
    extra_data = workstation.get("extra_data") if isinstance(workstation.get("extra_data"), dict) else {}
    values = {
        str(workstation_id or ""),
        str(workstation.get("id") or ""),
        str(workstation.get("config_id") or ""),
        str(workstation.get("name") or ""),
        str(workstation.get("agent_id") or ""),
        str(workstation.get("source_workstation_id") or ""),
        str(metadata.get("source_workstation_id") or ""),
        str(metadata.get("source_thread_id") or ""),
        str(metadata.get("bound_thread_id") or ""),
        str(extra_data.get("source_workstation_id") or ""),
        str(extra_data.get("source_thread_id") or ""),
        str(extra_data.get("bound_thread_id") or ""),
    }
    return {value.strip() for value in values if value and value.strip()}


def _workstation_adapter_hash(workstation: dict[str, object]) -> str:
    metadata = workstation.get("metadata") if isinstance(workstation.get("metadata"), dict) else {}
    extra_data = workstation.get("extra_data") if isinstance(workstation.get("extra_data"), dict) else {}
    return str(
        metadata.get("adapter_token_hash")
        or metadata.get("workstation_token_hash")
        or extra_data.get("adapter_token_hash")
        or extra_data.get("workstation_token_hash")
        or ""
    ).strip()


def _require_workstation_inbox_access(
    db: Session,
    request: Request,
    project_id: str,
    workstation_id: str,
    *,
    write: bool,
    action: str,
) -> dict[str, object]:
    workstation = get_project_thread_workstation(db, project_id, workstation_id)
    header_workstation_id = read_identity_header(request, "x-workstation-id")
    if not header_workstation_id:
        if write:
            resolve_project_write_principal(db, request, project_id, action=action)
        else:
            require_project_read_access(db, request, project_id, action=action)
        return workstation

    candidates = _workstation_identity_values(workstation_id, workstation)
    if header_workstation_id not in candidates:
        raise AppError(
            "PERMISSION_DENIED",
            f"{action} workstation id does not match",
            status_code=403,
            details={"project_id": project_id, "workstation_id": workstation_id, "header_workstation_id": header_workstation_id},
        )

    header_runner_id = read_identity_header(request, "x-runner-id")
    if header_runner_id:
        computer_node_id = _workstation_computer_node_id(workstation)
        if not computer_node_id:
            raise AppError(
                "PERMISSION_DENIED",
                f"{action} workstation is not bound to a computer",
                status_code=403,
                details={"project_id": project_id, "workstation_id": workstation_id},
            )
        node = db.scalar(
            select(ProjectComputerNode).where(
                ProjectComputerNode.project_id == project_id,
                ProjectComputerNode.config_id == computer_node_id,
            )
        )
        bound_runner_id = str(node.runner_id or "").strip() if node else ""
        if not bound_runner_id:
            raise AppError(
                "RUNNER_NOT_BOUND",
                f"{action} workstation computer is not bound to a runner",
                status_code=409,
                details={"project_id": project_id, "workstation_id": workstation_id, "computer_node_id": computer_node_id},
            )
        if header_runner_id != bound_runner_id:
            raise AppError(
                "PERMISSION_DENIED",
                f"{action} runner is not bound to this workstation computer",
                status_code=403,
                details={
                    "project_id": project_id,
                    "workstation_id": workstation_id,
                    "computer_node_id": computer_node_id,
                    "runner_id": header_runner_id,
                },
            )
        return workstation

    expected_hash = _workstation_adapter_hash(workstation)
    provided_token = str(request.headers.get("x-workstation-token") or "").strip()
    if expected_hash:
        provided_hash = hashlib.sha256(provided_token.encode("utf-8")).hexdigest() if provided_token else ""
        if not provided_hash or not hmac.compare_digest(provided_hash, expected_hash):
            raise AppError("PERMISSION_DENIED", "workstation token is invalid", status_code=403)
        mark_project_workstation_adapter_token_used(db, project_id, workstation_id)
    elif get_settings().app_env.lower() == "production":
        raise AppError("UNAUTHORIZED", "production workstation adapters require a workstation token", status_code=401)
    return workstation


@router.get("/users")
def api_list_users(request: Request, db: Session = Depends(get_db)):
    _require_real_human_principal(db, request)
    return ok([UserRead.model_validate(item).model_dump(mode="json") for item in list_users(db)])


@router.post("/users")
def api_create_user(payload: UserCreate, request: Request, db: Session = Depends(get_db)):
    _require_real_human_principal(db, request)
    return ok(UserRead.model_validate(create_user(db, payload)).model_dump(mode="json"))


@router.get("/users/{user_id}")
def api_get_user(user_id: str, request: Request, db: Session = Depends(get_db)):
    _require_real_human_principal(db, request)
    return ok(UserRead.model_validate(get_user_or_404(db, user_id)).model_dump(mode="json"))


@router.patch("/users/{user_id}")
def api_update_user(user_id: str, payload: UserUpdate, request: Request, db: Session = Depends(get_db)):
    _require_real_human_principal(db, request)
    return ok(UserRead.model_validate(update_user(db, user_id, payload)).model_dump(mode="json"))


@router.get("/invites")
def api_list_invites(project_id: str | None = None, status: str | None = None, request: Request = None, db: Session = Depends(get_db)):
    if project_id:
        require_project_read_access(db, request, project_id, action="collaboration.invite.read")
        scoped_project_ids = {project_id}
    else:
        scoped_project_ids = set(readable_project_ids(db, request))
    items = list_project_invites(db, project_id=project_id, status=status)
    if not project_id:
        items = [item for item in items if str(item.project_id or "") in scoped_project_ids]
    return ok([ProjectInviteRead.model_validate(serialize_project_invite_for_read(item)).model_dump(mode="json") for item in items])


@router.post("/projects/{project_id}/invites")
def api_create_invite(project_id: str, payload: ProjectInviteCreate, request: Request, db: Session = Depends(get_db)):
    principal = _require_real_human_principal(db, request)
    resolve_project_write_principal(db, request, project_id, require_privileged=True, action="collaboration.invite.create")
    return ok(
        ProjectInviteRead.model_validate(
            serialize_project_invite_for_read(
                create_project_invite(db, project_id, payload.model_copy(update={"invited_by_user_id": principal.user_id}))
            )
        ).model_dump(mode="json")
    )


@router.get("/invites/{invite_id}")
def api_get_invite(invite_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, _invite_project_id(db, invite_id), action="collaboration.invite.read")
    return ok(ProjectInviteRead.model_validate(serialize_project_invite_for_read(get_invite_or_404(db, invite_id))).model_dump(mode="json"))


@router.patch("/invites/{invite_id}")
def api_update_invite(invite_id: str, payload: ProjectInviteUpdate, request: Request, db: Session = Depends(get_db)):
    principal = _require_real_human_principal(db, request)
    invite = get_invite_or_404(db, invite_id)
    resolve_project_write_principal(db, request, invite.project_id, require_privileged=True, action="collaboration.invite.update")
    return ok(
        ProjectInviteRead.model_validate(
            serialize_project_invite_for_read(
                update_project_invite(db, invite_id, payload.model_copy(update={"accepted_by_user_id": principal.user_id}))
            )
        ).model_dump(mode="json")
    )


@router.post("/invites/{invite_id}/accept")
def api_accept_invite(invite_id: str, payload: ProjectInviteAcceptRequest, request: Request, db: Session = Depends(get_db)):
    principal = _require_real_human_principal(db, request)
    invite = get_invite_or_404(db, invite_id)
    current_user = get_user_or_404(db, principal.user_id) if principal.user_id else None
    if invite.email and current_user is not None and current_user.email != invite.email:
        raise AppError("INVITE_EMAIL_MISMATCH", "current identity does not match invite email", status_code=403)
    result = accept_invite(db, invite_id, payload.model_copy(update={"user_id": principal.user_id}))
    return ok(
        {
            "invite": ProjectInviteRead.model_validate(serialize_project_invite_for_read(result["invite"])).model_dump(mode="json"),
            "member": ProjectMemberRead.model_validate(result["member"]).model_dump(mode="json"),
            "user": UserRead.model_validate(result["user"]).model_dump(mode="json"),
        }
    )


@router.post("/invites/{invite_id}/revoke")
def api_revoke_invite(
    invite_id: str,
    request: Request,
    note: str | None = None,
    db: Session = Depends(get_db),
):
    principal = _require_real_human_principal(db, request)
    invite = get_invite_or_404(db, invite_id)
    resolve_project_write_principal(db, request, invite.project_id, require_privileged=True, action="collaboration.invite.revoke")
    return ok(
        ProjectInviteRead.model_validate(
            serialize_project_invite_for_read(
                revoke_invite(db, invite_id, actor_type="human", actor_id=principal.user_id, note=note)
            )
        ).model_dump(mode="json")
    )


@router.get("/projects/{project_id}/members")
def api_list_project_members(project_id: str, include_removed: bool = False, request: Request = None, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="collaboration.member.read")
    items = list_project_members(db, project_id, include_removed=include_removed)
    return ok([ProjectMemberRead.model_validate(item).model_dump(mode="json") for item in items])


@router.post("/projects/{project_id}/members")
def api_add_project_member(project_id: str, payload: ProjectMemberCreate, request: Request, db: Session = Depends(get_db)):
    _require_real_human_principal(db, request)
    resolve_project_write_principal(db, request, project_id, require_privileged=True, action="collaboration.member.create")
    return ok(ProjectMemberRead.model_validate(add_project_member(db, project_id, payload)).model_dump(mode="json"))


@router.patch("/projects/{project_id}/members/{member_id}")
def api_update_project_member(
    project_id: str, member_id: str, payload: ProjectMemberUpdate, request: Request, db: Session = Depends(get_db)
):
    _require_real_human_principal(db, request)
    resolve_project_write_principal(db, request, project_id, require_privileged=True, action="collaboration.member.update")
    return ok(ProjectMemberRead.model_validate(update_project_member(db, project_id, member_id, payload)).model_dump(mode="json"))


@router.delete("/projects/{project_id}/members/{member_id}")
def api_remove_project_member(
    project_id: str,
    member_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    principal = _require_real_human_principal(db, request)
    resolve_project_write_principal(db, request, project_id, require_privileged=True, action="collaboration.member.delete")
    return ok(
        ProjectMemberRead.model_validate(
            remove_project_member(db, project_id, member_id, actor_type="human", actor_id=principal.user_id)
        ).model_dump(mode="json")
    )


@router.get("/summary")
def api_collaboration_summary(request: Request, db: Session = Depends(get_db)):
    _require_real_human_principal(db, request)
    return ok(CollaborationSummaryRead.model_validate(get_collaboration_summary(db)).model_dump(mode="json"))


@router.get("/projects/{project_id}/config")
def api_get_project_config(project_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="project.collaboration_config.read")
    return ok(ProjectConfigRead.model_validate(get_project_collaboration_config(db, project_id)).model_dump(mode="json"))


@router.patch("/projects/{project_id}/config")
def api_update_project_config(project_id: str, payload: CollaborationConfigUpdate, request: Request, db: Session = Depends(get_db)):
    _require_real_human_principal(db, request)
    resolve_project_write_principal(db, request, project_id, require_privileged=True, action="project.collaboration_config.update")
    return ok(ProjectConfigRead.model_validate(update_project_collaboration_config(db, project_id, payload)).model_dump(mode="json"))


class WorkstationProfilePatch(BaseModel):
    local_repo_path: str | None = None
    review_policy: str | None = None
    skill_inheritance: list[str] | None = None
    knowledge_path: str | None = None
    lead_seat_id: str | None = None


def _seat_logical_workstation_key(seat: ProjectThreadWorkstation | None) -> str:
    """Logical workstation first; computer node is only the execution host fallback."""
    if seat is None:
        return ""
    workstation_id = str(getattr(seat, "workstation_id", "") or "").strip()
    if workstation_id:
        return workstation_id
    return str(getattr(seat, "computer_node_id", "") or "").strip()


def _seat_workstation_profile_key(seat: ProjectThreadWorkstation | None) -> str:
    key = _seat_logical_workstation_key(seat)
    return key or str(getattr(seat, "computer_node_id", "") or "").strip()


def _project_workstation_by_id_or_config(
    db: Session,
    project_id: str,
    workstation_ref: str,
) -> ProjectWorkstation | None:
    cleaned = str(workstation_ref or "").strip()
    if not cleaned:
        return None
    stmt = select(ProjectWorkstation).where(
        ProjectWorkstation.project_id == project_id,
        or_(ProjectWorkstation.id == cleaned, ProjectWorkstation.config_id == cleaned),
    )
    return db.scalar(stmt)


def _resolve_logical_workstation_lead_ref(
    db: Session,
    project_id: str,
    seat: ProjectThreadWorkstation,
    profiles: dict,
) -> str:
    ws_key = _seat_logical_workstation_key(seat)
    if getattr(seat, "workstation_id", None):
        logical_ws = _project_workstation_by_id_or_config(db, project_id, str(seat.workstation_id))
        if logical_ws and logical_ws.lead_seat_id:
            return str(logical_ws.lead_seat_id).strip()
        # Users often create a logical workstation with a product-facing id
        # ("frontend") while seats still carry an older group key ("planning").
        # If the exact workstation id is missing, find a registered workstation
        # whose lead belongs to the same logical group as the target seat.
        candidates = db.scalars(
            select(ProjectWorkstation).where(
                ProjectWorkstation.project_id == project_id,
                ProjectWorkstation.lead_seat_id.is_not(None),
            )
        )
        for candidate in candidates:
            lead_ref = str(candidate.lead_seat_id or "").strip()
            if not lead_ref:
                continue
            from app.modules.requirements.service import _resolve_seat

            lead_seat = _resolve_seat(db, project_id, lead_ref)
            if lead_seat is not None and _seat_logical_workstation_key(lead_seat) == ws_key:
                return lead_ref
    if isinstance(profiles, dict) and ws_key:
        profile = profiles.get(ws_key)
        if isinstance(profile, dict):
            return str(profile.get("lead_seat_id") or profile.get("leadSeatId") or "").strip()
    node_key = str(getattr(seat, "computer_node_id", "") or "").strip()
    if isinstance(profiles, dict) and node_key and node_key != ws_key:
        profile = profiles.get(node_key)
        if isinstance(profile, dict):
            return str(profile.get("lead_seat_id") or profile.get("leadSeatId") or "").strip()
    return ""


@router.patch("/projects/{project_id}/workstation-profiles/{node_id}")
def api_patch_workstation_profile(
    project_id: str,
    node_id: str,
    payload: WorkstationProfilePatch,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_real_human_principal(db, request)
    resolve_project_write_principal(db, request, project_id, require_privileged=True, action="project.workstation_profile.update")
    config = get_project_collaboration_config(db, project_id)
    inner = config.get("collaboration_config", {}) if isinstance(config.get("collaboration_config"), dict) else {}
    profiles = dict(inner.get("workstation_profiles") or {})
    current = dict(profiles.get(node_id) or {})
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        if v is None or v == "":
            current.pop(k, None)
        else:
            current[k] = v
    profiles[node_id] = current
    update_payload = CollaborationConfigUpdate(workstation_profiles=profiles)
    updated = update_project_collaboration_config(db, project_id, update_payload)
    return ok({"node_id": node_id, "profile": current, "config": ProjectConfigRead.model_validate(updated).model_dump(mode="json")})


class ProjectReviewPolicyPatch(BaseModel):
    default: str | None = None


class ProjectNpcPairReviewPolicyPatch(BaseModel):
    upstream_seat_id: str = Field(min_length=1)
    downstream_seat_id: str = Field(min_length=1)
    policy: str | None = None
    reason: str | None = None


class MessageReviewActionRequest(BaseModel):
    remember_pair_policy: str | None = None
    reason: str | None = None


def _runner_command_from_robotics_review(message: CollaborationMessage) -> RunnerRelayCommandCreate | None:
    if str(message.message_type or "").strip() != "robotics_terminal_npc_request":
        return None
    metadata = message.extra_data if isinstance(message.extra_data, dict) else {}
    computer_node_id = str(metadata.get("computer_node_id") or "").strip()
    command = str(metadata.get("terminal_command") or "").strip()
    if not computer_node_id or not command:
        return None
    interface_name = str(metadata.get("terminal_interface_name") or "").strip()
    interface_kind = str(metadata.get("terminal_interface_kind") or "").strip()
    npc_label = str(metadata.get("terminal_bound_npc") or message.sender_id or "NPC").strip()
    body = "\n".join(
        line
        for line in [
            "用户已通过 NPC 代操作审核，请在目标电脑调试终端执行并回写最小回执。",
            f"协助 NPC：{npc_label}",
            f"接口类型：{interface_kind or '待确认'}",
            f"接口名称：{interface_name or str(metadata.get('terminal_interface_id') or '').strip()}",
            f"审核后命令：{command}",
            "边界：只执行本次审核通过的终端操作；新的写入、发送、运动、固件或 ROS 写操作必须重新申请审核。",
        ]
        if line
    )
    return RunnerRelayCommandCreate(
        title=f"审核通过的 NPC 终端操作：{interface_name or interface_kind or '调试终端'}",
        body=body,
        computer_node_id=computer_node_id,
        metadata={
            **metadata,
            "terminal_mode": "npc_terminal_approved",
            "review_message_id": message.id,
        },
    )


@router.patch("/projects/{project_id}/review-policy")
def api_patch_project_review_policy(
    project_id: str,
    payload: ProjectReviewPolicyPatch,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_real_human_principal(db, request)
    resolve_project_write_principal(db, request, project_id, require_privileged=True, action="project.review_policy.update")
    config = get_project_collaboration_config(db, project_id)
    inner = config.get("collaboration_config", {}) if isinstance(config.get("collaboration_config"), dict) else {}
    rp = dict(inner.get("review_policy") or {})
    data = payload.model_dump(exclude_unset=True)
    if "default" in data:
        if data["default"]:
            rp["default"] = data["default"]
        else:
            rp.pop("default", None)
    updated = update_project_collaboration_config(db, project_id, CollaborationConfigUpdate(review_policy=rp))
    return ok({"review_policy": rp, "config": ProjectConfigRead.model_validate(updated).model_dump(mode="json")})


def _set_npc_pair_review_policy(
    db: Session,
    project_id: str,
    *,
    upstream_seat_id: str,
    downstream_seat_id: str,
    policy: str | None,
    actor_id: str,
    reason: str | None = None,
) -> dict[str, object]:
    from app.modules.requirements.service import _resolve_seat

    upstream = _resolve_seat(db, project_id, upstream_seat_id)
    downstream = _resolve_seat(db, project_id, downstream_seat_id)
    if upstream is None or downstream is None:
        raise AppError("NPC_PAIR_NOT_FOUND", "找不到这对 NPC，请刷新工作台后重试", status_code=404)

    normalized = str(policy or "").strip().lower()
    config = get_project_collaboration_config(db, project_id)
    inner = config.get("collaboration_config", {}) if isinstance(config.get("collaboration_config"), dict) else {}
    rp = dict(inner.get("review_policy") or {})
    pair_rules = dict(rp.get("npc_pair_rules") or {})
    pair_key = f"{upstream.id}->{downstream.id}"

    if normalized in {"", "inherit", "default", "off", "remove", "none"}:
        pair_rules.pop(pair_key, None)
        effective_policy = "inherit"
    elif normalized in {"skip", "never", "免审"}:
        effective_policy = "skip"
        pair_rules[pair_key] = {
            "policy": "skip",
            "upstream_seat_id": upstream.id,
            "upstream_name": upstream.name,
            "downstream_seat_id": downstream.id,
            "downstream_name": downstream.name,
            "updated_by": actor_id,
            "updated_at": datetime.now(UTC).isoformat(),
            "reason": reason or "trusted from review flow",
        }
    elif normalized in {"force", "always", "强审"}:
        effective_policy = "force"
        pair_rules[pair_key] = {
            "policy": "force",
            "upstream_seat_id": upstream.id,
            "upstream_name": upstream.name,
            "downstream_seat_id": downstream.id,
            "downstream_name": downstream.name,
            "updated_by": actor_id,
            "updated_at": datetime.now(UTC).isoformat(),
            "reason": reason or "forced human review",
        }
    else:
        raise AppError("INVALID_REVIEW_POLICY", "policy must be skip, force, or inherit", status_code=422)

    if pair_rules:
        rp["npc_pair_rules"] = pair_rules
    else:
        rp.pop("npc_pair_rules", None)
    updated = update_project_collaboration_config(db, project_id, CollaborationConfigUpdate(review_policy=rp))
    return {
        "pair_key": pair_key,
        "policy": effective_policy,
        "upstream_seat_id": upstream.id,
        "upstream_name": upstream.name,
        "downstream_seat_id": downstream.id,
        "downstream_name": downstream.name,
        "review_policy": rp,
        "config": ProjectConfigRead.model_validate(updated).model_dump(mode="json"),
    }


@router.patch("/projects/{project_id}/review-policy/npc-pairs")
def api_patch_project_npc_pair_review_policy(
    project_id: str,
    payload: ProjectNpcPairReviewPolicyPatch,
    request: Request,
    db: Session = Depends(get_db),
):
    principal = _require_real_human_principal(db, request)
    resolve_project_write_principal(db, request, project_id, require_privileged=False, action="project.review_policy.npc_pair.update")
    return ok(
        _set_npc_pair_review_policy(
            db,
            project_id,
            upstream_seat_id=payload.upstream_seat_id,
            downstream_seat_id=payload.downstream_seat_id,
            policy=payload.policy,
            actor_id=principal.user_id,
            reason=payload.reason,
        )
    )


@router.get("/projects/{project_id}/ai-providers")
def api_list_project_ai_providers(project_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="project.collaboration_provider.read")
    items = list_project_ai_providers(db, project_id)
    return ok([CollaborationProviderRead.model_validate(item).model_dump(mode="json") for item in items])


@router.get("/projects/{project_id}/ai-providers/{provider_id}")
def api_get_project_ai_provider(project_id: str, provider_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="project.collaboration_provider.read")
    return ok(CollaborationProviderRead.model_validate(get_project_ai_provider(db, project_id, provider_id)).model_dump(mode="json"))


@router.post("/projects/{project_id}/ai-providers")
def api_create_project_ai_provider(project_id: str, payload: CollaborationProviderCreate, request: Request, db: Session = Depends(get_db)):
    _require_real_human_principal(db, request)
    resolve_project_write_principal(db, request, project_id, require_privileged=True, action="project.collaboration_provider.create")
    return ok(CollaborationProviderRead.model_validate(create_project_ai_provider(db, project_id, payload)).model_dump(mode="json"))


@router.patch("/projects/{project_id}/ai-providers/{provider_id}")
def api_update_project_ai_provider(project_id: str, provider_id: str, payload: CollaborationProviderUpdate, request: Request, db: Session = Depends(get_db)):
    _require_real_human_principal(db, request)
    resolve_project_write_principal(db, request, project_id, require_privileged=True, action="project.collaboration_provider.update")
    return ok(CollaborationProviderRead.model_validate(update_project_ai_provider(db, project_id, provider_id, payload)).model_dump(mode="json"))


@router.delete("/projects/{project_id}/ai-providers/{provider_id}")
def api_delete_project_ai_provider(project_id: str, provider_id: str, request: Request, db: Session = Depends(get_db)):
    _require_real_human_principal(db, request)
    resolve_project_write_principal(db, request, project_id, require_privileged=True, action="project.collaboration_provider.delete")
    return ok(CollaborationProviderRead.model_validate(delete_project_ai_provider(db, project_id, provider_id)).model_dump(mode="json"))


@router.get("/projects/{project_id}/computer-nodes")
def api_list_project_computer_nodes(project_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="project.collaboration_node.read")
    items = list_project_computer_nodes(db, project_id)
    return ok([CollaborationComputerNodeRead.model_validate(item).model_dump(mode="json") for item in items])


@router.get("/projects/{project_id}/computer-nodes/{node_id}")
def api_get_project_computer_node(project_id: str, node_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="project.collaboration_node.read")
    return ok(CollaborationComputerNodeRead.model_validate(get_project_computer_node(db, project_id, node_id)).model_dump(mode="json"))


@router.get("/projects/{project_id}/computer-nodes/{node_id}/pairing-token")
def api_get_project_computer_node_pairing_token(
    project_id: str,
    node_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    _resolve_computer_node_manager_principal(
        db,
        request,
        project_id=project_id,
        node_id=node_id,
        action="project.collaboration_node.pairing.read",
    )
    return ok(
        ComputerNodePairingTokenRead.model_validate(
            get_project_computer_node_pairing_status(db, project_id, node_id)
        ).model_dump(mode="json")
    )


@router.post("/projects/{project_id}/computer-nodes/{node_id}/pairing-token")
def api_rotate_project_computer_node_pairing_token(
    project_id: str,
    node_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    _resolve_computer_node_manager_principal(
        db,
        request,
        project_id=project_id,
        node_id=node_id,
        action="project.collaboration_node.pairing.rotate",
    )
    return ok(
        ComputerNodePairingTokenRead.model_validate(
            rotate_project_computer_node_pairing_token(db, project_id, node_id)
        ).model_dump(mode="json")
    )


@router.delete("/projects/{project_id}/computer-nodes/{node_id}/pairing-token")
def api_revoke_project_computer_node_pairing_token(
    project_id: str,
    node_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    _resolve_computer_node_manager_principal(
        db,
        request,
        project_id=project_id,
        node_id=node_id,
        action="project.collaboration_node.pairing.revoke",
    )
    return ok(
        ComputerNodePairingTokenRead.model_validate(
            revoke_project_computer_node_pairing_token(db, project_id, node_id)
        ).model_dump(mode="json")
    )


@router.post("/projects/{project_id}/computer-nodes")
def api_create_project_computer_node(project_id: str, payload: CollaborationComputerNodeCreate, request: Request, db: Session = Depends(get_db)):
    principal = _require_real_human_principal(db, request)
    resolve_project_write_principal(db, request, project_id, action="project.collaboration_node.create")
    current_user = get_user_or_404(db, principal.user_id) if principal.user_id else None
    metadata = dict(payload.metadata or {})
    metadata.setdefault("owner_user_id", principal.user_id)
    metadata.setdefault("owner_name", current_user.name if current_user else None)
    metadata.setdefault("owner_email", current_user.email if current_user else None)
    metadata.setdefault("source", metadata.get("source") or "user_project_workbench")
    next_payload = payload.model_copy(update={"metadata": metadata})
    return ok(
        CollaborationComputerNodeRead.model_validate(create_project_computer_node(db, project_id, next_payload)).model_dump(mode="json")
    )


@router.patch("/projects/{project_id}/computer-nodes/{node_id}")
def api_update_project_computer_node(project_id: str, node_id: str, payload: CollaborationComputerNodeUpdate, request: Request, db: Session = Depends(get_db)):
    _resolve_computer_node_manager_principal(
        db,
        request,
        project_id=project_id,
        node_id=node_id,
        action="project.collaboration_node.update",
    )
    return ok(CollaborationComputerNodeRead.model_validate(update_project_computer_node(db, project_id, node_id, payload)).model_dump(mode="json"))


@router.delete("/projects/{project_id}/computer-nodes/{node_id}")
def api_delete_project_computer_node(project_id: str, node_id: str, request: Request, db: Session = Depends(get_db)):
    _resolve_computer_node_manager_principal(
        db,
        request,
        project_id=project_id,
        node_id=node_id,
        action="project.collaboration_node.delete",
    )
    return ok(CollaborationComputerNodeRead.model_validate(delete_project_computer_node(db, project_id, node_id)).model_dump(mode="json"))


@router.get("/projects/{project_id}/thread-workstations")
def api_list_project_thread_workstations(project_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="project.collaboration_workstation.read")
    items = list_project_thread_workstations(db, project_id)
    return ok([CollaborationWorkstationRead.model_validate(item).model_dump(mode="json") for item in items])


@router.get("/projects/{project_id}/thread-workstations/{workstation_id}")
def api_get_project_thread_workstation(project_id: str, workstation_id: str, request: Request, db: Session = Depends(get_db)):
    require_project_read_access(db, request, project_id, action="project.collaboration_workstation.read")
    return ok(
        CollaborationWorkstationRead.model_validate(
            get_project_thread_workstation(
                db,
                project_id,
                workstation_id,
                allow_historical_alias=True,
            )
        ).model_dump(mode="json")
    )


@router.post("/projects/{project_id}/thread-workstations")
def api_create_project_thread_workstation(
    project_id: str,
    payload: CollaborationWorkstationCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    _resolve_workstation_manager_principal(
        db,
        request,
        project_id=project_id,
        computer_node_id=payload.computer_node_id or payload.computer_node,
        action="project.collaboration_workstation.create",
    )
    return ok(CollaborationWorkstationRead.model_validate(create_project_thread_workstation(db, project_id, payload)).model_dump(mode="json"))


_OCCUPANCY_HEARTBEAT_TIMEOUT_SECONDS = 90


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        from datetime import datetime
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _resolve_occupancy(seat: dict) -> dict | None:
    metadata = seat.get("metadata") if isinstance(seat.get("metadata"), dict) else {}
    extra = seat.get("extra_data") if isinstance(seat.get("extra_data"), dict) else {}
    occ = (metadata.get("occupancy") if isinstance(metadata.get("occupancy"), dict) else None) or \
          (extra.get("occupancy") if isinstance(extra.get("occupancy"), dict) else None)
    if not occ:
        return None
    if not occ.get("user_id"):
        return None
    import time
    age = time.time() - _parse_iso(occ.get("heartbeat_at") or occ.get("acquired_at"))
    if age > _OCCUPANCY_HEARTBEAT_TIMEOUT_SECONDS:
        return None
    return occ


class OccupancyClaimPayload(BaseModel):
    force: bool = False
    user_name: str | None = None


@router.post("/projects/{project_id}/thread-workstations/{workstation_id}/occupy")
def api_occupy_seat(
    project_id: str,
    workstation_id: str,
    payload: OccupancyClaimPayload,
    request: Request,
    db: Session = Depends(get_db),
):
    principal = _require_real_human_principal(db, request)
    resolve_project_write_principal(db, request, project_id, action="project.collaboration_workstation.occupy")
    seat = get_project_thread_workstation(db, project_id, workstation_id)
    current = _resolve_occupancy(seat)
    me = principal.user_id or principal.actor_id
    if current and current.get("user_id") != me and not payload.force:
        return ok({
            "ok": False,
            "occupied_by": current,
            "seat_id": seat.get("id") or seat.get("config_id"),
        })
    metadata = dict(seat.get("metadata") or {}) if isinstance(seat.get("metadata"), dict) else {}
    now = _now_iso()
    metadata["occupancy"] = {
        "user_id": me,
        "user_name": payload.user_name or current and current.get("user_name") or me,
        "acquired_at": current.get("acquired_at") if (current and current.get("user_id") == me) else now,
        "heartbeat_at": now,
        "preempted": bool(current and current.get("user_id") != me and payload.force),
        "preempted_user": current.get("user_id") if (current and current.get("user_id") != me and payload.force) else None,
    }
    update_payload = CollaborationWorkstationUpdate(metadata=metadata)
    update_project_thread_workstation(db, project_id, workstation_id, update_payload)
    return ok({"ok": True, "occupancy": metadata["occupancy"]})


@router.post("/projects/{project_id}/thread-workstations/{workstation_id}/release")
def api_release_seat(
    project_id: str,
    workstation_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    principal = _require_real_human_principal(db, request)
    resolve_project_write_principal(db, request, project_id, action="project.collaboration_workstation.release")
    seat = get_project_thread_workstation(db, project_id, workstation_id)
    current = _resolve_occupancy(seat)
    me = principal.user_id or principal.actor_id
    if current and current.get("user_id") != me:
        return ok({"ok": False, "reason": "not the holder", "occupied_by": current})
    metadata = dict(seat.get("metadata") or {}) if isinstance(seat.get("metadata"), dict) else {}
    metadata["occupancy"] = None
    update_payload = CollaborationWorkstationUpdate(metadata=metadata)
    update_project_thread_workstation(db, project_id, workstation_id, update_payload)
    return ok({"ok": True})


@router.get("/projects/{project_id}/thread-workstations/{workstation_id}/occupancy")
def api_get_seat_occupancy(
    project_id: str,
    workstation_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    require_project_read_access(db, request, project_id, action="project.collaboration_workstation.occupancy.read")
    seat = get_project_thread_workstation(db, project_id, workstation_id)
    current = _resolve_occupancy(seat)
    return ok({"occupancy": current})


@router.patch("/projects/{project_id}/thread-workstations/{workstation_id}")
def api_update_project_thread_workstation(
    project_id: str,
    workstation_id: str,
    payload: CollaborationWorkstationUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    workstation = get_project_thread_workstation(db, project_id, workstation_id)
    _resolve_workstation_manager_principal(
        db,
        request,
        project_id=project_id,
        computer_node_id=_workstation_computer_node_id(workstation),
        action="project.collaboration_workstation.update",
    )
    return ok(CollaborationWorkstationRead.model_validate(update_project_thread_workstation(db, project_id, workstation_id, payload)).model_dump(mode="json"))


@router.delete("/projects/{project_id}/thread-workstations/{workstation_id}")
def api_delete_project_thread_workstation(project_id: str, workstation_id: str, request: Request, db: Session = Depends(get_db)):
    workstation = get_project_thread_workstation(db, project_id, workstation_id)
    _resolve_workstation_manager_principal(
        db,
        request,
        project_id=project_id,
        computer_node_id=_workstation_computer_node_id(workstation),
        action="project.collaboration_workstation.delete",
    )
    return ok(CollaborationWorkstationRead.model_validate(delete_project_thread_workstation(db, project_id, workstation_id)).model_dump(mode="json"))


@router.post("/projects/{project_id}/thread-workstations/{workstation_id}/messages")
def api_create_workstation_message(
    project_id: str,
    workstation_id: str,
    payload: CollaborationMessageCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_real_human_principal(db, request)
    resolve_project_write_principal(db, request, project_id, action="collaboration.workstation_message.create")
    workstation = get_project_thread_workstation(db, project_id, workstation_id)
    if payload.message_type in {"runner_command", "runner_ack", "runner_result"}:
        raise AppError("FORBIDDEN_MESSAGE_TYPE", "runner relay 消息必须走专用接口", status_code=403)
    item = create_collaboration_message(
        db,
        payload.model_copy(
            update={
                "project_id": project_id,
                "agent_id": workstation_id,
                "sender_type": "agent",
                "sender_id": workstation_id,
            }
        ),
    )
    return ok(
        {
            "message": CollaborationMessageRead.model_validate(item).model_dump(mode="json"),
            "workstation": CollaborationWorkstationRead.model_validate(workstation).model_dump(mode="json"),
        }
    )


@router.post("/projects/{project_id}/thread-workstations/{workstation_id}/structured-need")
def api_create_workstation_structured_need(
    project_id: str,
    workstation_id: str,
    payload: StructuredNeedCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    workstation = _require_workstation_inbox_access(
        db,
        request,
        project_id,
        workstation_id,
        write=True,
        action="collaboration.workstation_structured_need.create",
    )
    requester_id = str(workstation.get("row_id") or workstation.get("id") or workstation_id).strip() or workstation_id
    result = create_structured_need(
        db,
        payload.model_copy(
            update={
                "project_id": project_id,
                "requester_seat_id": requester_id,
            }
        ),
    )
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


@router.get("/projects/{project_id}/thread-workstations/{workstation_id}/inbox")
def api_get_workstation_inbox(
    project_id: str,
    workstation_id: str,
    request: Request,
    status: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    _require_workstation_inbox_access(
        db,
        request,
        project_id,
        workstation_id,
        write=False,
        action="collaboration.workstation_inbox.read",
    )
    items = list_workstation_inbox_messages(db, project_id, workstation_id, status=status, limit=limit)
    return ok([CollaborationMessageRead.model_validate(item).model_dump(mode="json") for item in items])


@router.get("/projects/{project_id}/thread-workstations/{workstation_id}/queues")
def api_get_workstation_queues(
    project_id: str,
    workstation_id: str,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    workstation = _require_workstation_inbox_access(
        db,
        request,
        project_id,
        workstation_id,
        write=False,
        action="collaboration.workstation_queues.read",
    )
    seat_id = str(workstation.get("row_id") or workstation.get("id") or workstation_id).strip() or workstation_id
    return ok(get_seat_queues(db, seat_id, project_id=project_id, limit=limit))


@router.post("/projects/{project_id}/thread-workstations/{workstation_id}/desktop-sync")
def api_sync_desktop_thread_event(
    project_id: str,
    workstation_id: str,
    payload: DesktopThreadSyncCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    workstation = _require_workstation_inbox_access(
        db,
        request,
        project_id,
        workstation_id,
        write=True,
        action="collaboration.workstation_desktop_sync.write",
    )
    role = payload.role.strip().lower()
    note = payload.note.strip()
    received_at = datetime.now(UTC)
    sync_latency_ms = None
    if payload.source_timestamp:
        try:
            source_timestamp = datetime.fromisoformat(payload.source_timestamp.replace("Z", "+00:00"))
            if source_timestamp.tzinfo is None:
                source_timestamp = source_timestamp.replace(tzinfo=UTC)
            sync_latency_ms = max(0, int((received_at - source_timestamp.astimezone(UTC)).total_seconds() * 1000))
        except ValueError:
            sync_latency_ms = None
    metadata = dict(payload.metadata or {})
    canonical_workstation_id = str(workstation.get("id") or workstation.get("config_id") or workstation_id).strip() or workstation_id
    user_visible_workstation_id = workstation_id
    metadata.update(
        {
            "source": "desktop_thread_sync",
            "desktop_sync": True,
            "desktop_role": role,
            "desktop_phase": payload.phase,
            "desktop_session_id": payload.session_id,
            "desktop_source_event_id": payload.source_event_id,
            "desktop_source_timestamp": payload.source_timestamp,
            "desktop_sync_received_at": received_at.isoformat(),
            "desktop_sync_latency_ms": sync_latency_ms,
            "linked_message_id": payload.linked_message_id,
            "requested_workstation_id": user_visible_workstation_id,
            "canonical_workstation_id": canonical_workstation_id,
            "authoritative_seat_id": canonical_workstation_id,
            "authoritative_seat_ref": canonical_workstation_id,
            "historical_alias_non_authoritative": user_visible_workstation_id != canonical_workstation_id,
        }
    )
    source_key = payload.source_event_id or f"{payload.session_id or workstation_id}:{payload.source_timestamp or ''}:{role}:{note[:80]}"
    dedupe_key = f"desktop_sync:{project_id}:{workstation_id}:{source_key}"[:128]
    message_type = "desktop_user_question" if role == "user" else "desktop_minimal_receipt"
    existing = db.scalar(
        select(CollaborationMessage)
        .where(CollaborationMessage.dedupe_key == dedupe_key)
        .limit(1)
    )
    if existing is not None:
        return ok({"message": CollaborationMessageRead.model_validate(existing).model_dump(mode="json"), "deduped": True})
    item = create_collaboration_message(
        db,
        CollaborationMessageCreate(
            project_id=project_id,
            agent_id=canonical_workstation_id,
            message_type=message_type,
            title="Desktop 提问" if role == "user" else "Desktop 最小回执",
            body=note,
            sender_type="human" if role == "user" else "agent",
            sender_id="desktop-user" if role == "user" else canonical_workstation_id,
            recipient_type="thread_workstation" if role == "user" else "human",
            recipient_id=canonical_workstation_id if role == "user" else "desktop-user",
            status="open" if role == "user" else "delivered",
            metadata=metadata,
        ),
        dispatch_id=None,
        dedupe_key=dedupe_key,
    )
    return ok({"message": CollaborationMessageRead.model_validate(item).model_dump(mode="json"), "deduped": False})


@router.get("/projects/{project_id}/thread-workstations/{workstation_id}/adapter-config")
def api_get_workstation_adapter_config(
    project_id: str,
    workstation_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_workstation_inbox_access(
        db,
        request,
        project_id,
        workstation_id,
        write=False,
        action="collaboration.workstation_adapter_config.read",
    )
    config = get_project_workstation_adapter_config(db, project_id, workstation_id)
    return ok(WorkstationAdapterConfigRead.model_validate(config).model_dump(mode="json"))


@router.get("/projects/{project_id}/thread-workstations/{workstation_id}/adapter-token")
def api_get_workstation_adapter_token(
    project_id: str,
    workstation_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    workstation = get_project_thread_workstation(db, project_id, workstation_id)
    _resolve_workstation_manager_principal(
        db,
        request,
        project_id=project_id,
        computer_node_id=_workstation_computer_node_id(workstation),
        action="project.collaboration_workstation.adapter_token.read",
    )
    status = get_project_workstation_adapter_token_status(db, project_id, workstation_id)
    return ok(WorkstationAdapterTokenRead.model_validate(status).model_dump(mode="json"))


@router.post("/projects/{project_id}/thread-workstations/{workstation_id}/adapter-token")
def api_rotate_workstation_adapter_token(
    project_id: str,
    workstation_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    workstation = get_project_thread_workstation(db, project_id, workstation_id)
    _resolve_workstation_manager_principal(
        db,
        request,
        project_id=project_id,
        computer_node_id=_workstation_computer_node_id(workstation),
        action="project.collaboration_workstation.adapter_token.rotate",
    )
    status = rotate_project_workstation_adapter_token(db, project_id, workstation_id)
    return ok(WorkstationAdapterTokenRead.model_validate(status).model_dump(mode="json"))


@router.delete("/projects/{project_id}/thread-workstations/{workstation_id}/adapter-token")
def api_revoke_workstation_adapter_token(
    project_id: str,
    workstation_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    workstation = get_project_thread_workstation(db, project_id, workstation_id)
    _resolve_workstation_manager_principal(
        db,
        request,
        project_id=project_id,
        computer_node_id=_workstation_computer_node_id(workstation),
        action="project.collaboration_workstation.adapter_token.revoke",
    )
    status = revoke_project_workstation_adapter_token(db, project_id, workstation_id)
    return ok(WorkstationAdapterTokenRead.model_validate(status).model_dump(mode="json"))


@router.post("/projects/{project_id}/thread-workstations/{workstation_id}/messages/{message_id}/ack")
def api_ack_workstation_message(
    project_id: str,
    workstation_id: str,
    message_id: str,
    payload: WorkstationInboxAckCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_workstation_inbox_access(
        db,
        request,
        project_id,
        workstation_id,
        write=True,
        action="collaboration.workstation_inbox.ack",
    )
    result = ack_workstation_command(db, project_id, workstation_id, message_id, payload)
    return ok(
        {
            "command": CollaborationMessageRead.model_validate(result["command"]).model_dump(mode="json"),
            "receipt": (
                CollaborationMessageRead.model_validate(result["receipt"]).model_dump(mode="json")
                if result["receipt"] is not None
                else None
            ),
        }
    )


@router.post("/projects/{project_id}/thread-workstations/{workstation_id}/messages/{message_id}/complete")
def api_complete_workstation_message(
    project_id: str,
    workstation_id: str,
    message_id: str,
    payload: WorkstationInboxCompleteCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_workstation_inbox_access(
        db,
        request,
        project_id,
        workstation_id,
        write=True,
        action="collaboration.workstation_inbox.complete",
    )
    result = complete_workstation_command(db, project_id, workstation_id, message_id, payload)
    return ok(
        {
            "command": CollaborationMessageRead.model_validate(result["command"]).model_dump(mode="json"),
            "receipt": (
                CollaborationMessageRead.model_validate(result["receipt"]).model_dump(mode="json")
                if result["receipt"] is not None
                else None
            ),
        }
    )


@router.post("/projects/{project_id}/thread-workstations/{workstation_id}/messages/{message_id}/progress")
def api_progress_workstation_message(
    project_id: str,
    workstation_id: str,
    message_id: str,
    payload: WorkstationInboxProgressCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_workstation_inbox_access(
        db,
        request,
        project_id,
        workstation_id,
        write=True,
        action="collaboration.workstation_inbox.progress",
    )
    result = progress_workstation_command(db, project_id, workstation_id, message_id, payload)
    return ok(
        {
            "command": CollaborationMessageRead.model_validate(result["command"]).model_dump(mode="json"),
            "receipt": CollaborationMessageRead.model_validate(result["receipt"]).model_dump(mode="json"),
        }
    )


@router.post("/projects/{project_id}/thread-workstations/{workstation_id}/messages/{message_id}/closeout-action")
def api_closeout_workstation_message(
    project_id: str,
    workstation_id: str,
    message_id: str,
    payload: DesktopCloseoutActionCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    principal = resolve_project_write_principal(
        db,
        request,
        project_id,
        require_privileged=False,
        action="collaboration.workstation_inbox.closeout_action",
    )
    result = closeout_workstation_command(
        db,
        project_id,
        workstation_id,
        message_id,
        action=payload.action,
        note=payload.note,
        actor_type=principal.actor_type,
        actor_id=principal.actor_id,
    )
    return ok(
        {
            "command": CollaborationMessageRead.model_validate(result["command"]).model_dump(mode="json"),
            "receipt": CollaborationMessageRead.model_validate(result["receipt"]).model_dump(mode="json"),
        }
    )


@router.get("/messages")
def api_list_messages(
    project_id: str | None = None,
    task_id: str | None = None,
    approval_id: str | None = None,
    handoff_id: str | None = None,
    requirement_id: str | None = None,
    agent_id: str | None = None,
    message_type: str | None = None,
    recipient_type: str | None = None,
    recipient_id: str | None = None,
    sender_id: str | None = None,
    status: str | None = None,
    request: Request = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    _require_real_human_principal(db, request)
    scoped_project_id = _collaboration_message_scope_project_id(
        db,
        project_id=project_id,
        task_id=task_id,
        approval_id=approval_id,
        handoff_id=handoff_id,
        requirement_id=requirement_id,
        agent_id=agent_id,
    )
    require_project_read_access(db, request, scoped_project_id, action="collaboration.message.read")
    items = list_messages(
        db,
        project_id=scoped_project_id,
        task_id=task_id,
        approval_id=approval_id,
        handoff_id=handoff_id,
        requirement_id=requirement_id,
        agent_id=agent_id,
        message_type=message_type,
        recipient_type=recipient_type,
        recipient_id=recipient_id,
        sender_id=sender_id,
        status=status,
        limit=limit,
    )
    return ok([CollaborationMessageRead.model_validate(item).model_dump(mode="json") for item in items])


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _safe_artifact_text_path(raw_path: str) -> Path:
    cleaned = str(raw_path or "").strip().strip('"').strip("'")
    if not cleaned:
        raise AppError("ARTIFACT_PATH_REQUIRED", "artifact path is required", status_code=400)
    cleaned = cleaned.replace("\\", "/")
    lowered = cleaned.lower()
    marker = "/artifacts/"
    if marker in lowered:
        cleaned = cleaned[lowered.index(marker) + 1 :]
    elif lowered.startswith("artifacts/"):
        cleaned = cleaned
    else:
        raise AppError("ARTIFACT_PATH_NOT_ALLOWED", "only files under artifacts/ can be previewed", status_code=400)
    if "\x00" in cleaned or ".." in Path(cleaned).parts:
        raise AppError("ARTIFACT_PATH_NOT_ALLOWED", "artifact path is not allowed", status_code=400)
    path = (_repo_root() / cleaned).resolve()
    artifacts_root = (_repo_root() / "artifacts").resolve()
    try:
        path.relative_to(artifacts_root)
    except ValueError as exc:
        raise AppError("ARTIFACT_PATH_NOT_ALLOWED", "artifact path is outside artifacts/", status_code=400) from exc
    if not path.is_file():
        raise AppError("ARTIFACT_NOT_FOUND", "artifact file not found", status_code=404)
    if path.suffix.lower() not in {".md", ".txt", ".log", ".json", ".jsonl", ".yaml", ".yml"}:
        raise AppError("ARTIFACT_TYPE_NOT_PREVIEWABLE", "only text artifacts can be previewed", status_code=400)
    return path


@router.get("/artifacts/preview")
def api_preview_project_artifact_legacy_order(
    project_id: str = Query(..., min_length=1, max_length=120),
    path: str = Query(..., min_length=1, max_length=1200),
    task_id: str | None = Query(default=None, min_length=1, max_length=120),
    dispatch_id: str | None = Query(default=None, min_length=1, max_length=120),
    source_message_id: str | None = Query(default=None, min_length=1, max_length=120),
    workstation_id: str | None = Query(default=None, min_length=1, max_length=120),
    request: Request = None,
    db: Session = Depends(get_db),
):
    return _preview_project_artifact(
        db,
        request,
        project_id,
        path,
        task_id=task_id,
        dispatch_id=dispatch_id,
        source_message_id=source_message_id,
        workstation_id=workstation_id,
    )


@router.get("/projects/{project_id}/artifacts/preview")
def api_preview_project_artifact(
    project_id: str,
    path: str = Query(..., min_length=1, max_length=1200),
    task_id: str | None = Query(default=None, min_length=1, max_length=120),
    dispatch_id: str | None = Query(default=None, min_length=1, max_length=120),
    source_message_id: str | None = Query(default=None, min_length=1, max_length=120),
    workstation_id: str | None = Query(default=None, min_length=1, max_length=120),
    request: Request = None,
    db: Session = Depends(get_db),
):
    return _preview_project_artifact(
        db,
        request,
        project_id,
        path,
        task_id=task_id,
        dispatch_id=dispatch_id,
        source_message_id=source_message_id,
        workstation_id=workstation_id,
    )


def _artifact_preview_scope_requested(
    *,
    task_id: str | None,
    dispatch_id: str | None,
    source_message_id: str | None,
    workstation_id: str | None,
) -> bool:
    return any(str(value or "").strip() for value in (task_id, dispatch_id, source_message_id, workstation_id))


def _assert_artifact_preview_scope(
    db: Session,
    *,
    project_id: str,
    artifact_path: str,
    task_id: str | None,
    dispatch_id: str | None,
    source_message_id: str | None,
    workstation_id: str | None,
) -> None:
    cleaned_task_id = str(task_id or "").strip()
    if not cleaned_task_id:
        raise AppError("ARTIFACT_CONTEXT_REQUIRED", "task_id is required for scoped artifact preview", status_code=400)

    task = db.get(Task, cleaned_task_id)
    if task is None or str(task.project_id or "") != str(project_id or ""):
        raise AppError("ARTIFACT_CONTEXT_NOT_FOUND", "artifact preview context was not found in this project", status_code=404)

    from app.modules.tasks.service import get_task_artifact_index

    cleaned_dispatch_id = str(dispatch_id or "").strip()
    cleaned_source_message_id = str(source_message_id or "").strip()
    cleaned_workstation_id = str(workstation_id or "").strip()
    for entry in get_task_artifact_index(db, cleaned_task_id):
        if str(entry.get("path") or "").replace("\\", "/") != artifact_path:
            continue
        if cleaned_dispatch_id and str(entry.get("dispatch_id") or "") != cleaned_dispatch_id:
            continue
        if cleaned_source_message_id and str(entry.get("source_message_id") or "") != cleaned_source_message_id:
            continue
        if cleaned_workstation_id:
            candidates = {
                str(entry.get("workstation_id") or ""),
                str(entry.get("sender_id") or ""),
                str(entry.get("authoritative_seat_id") or ""),
                str(entry.get("authoritative_target_seat_id") or ""),
            }
            if cleaned_workstation_id not in candidates:
                continue
        return

    raise AppError(
        "ARTIFACT_NOT_IN_CONTEXT",
        "artifact is not registered in this task evidence chain",
        status_code=403,
    )


def _preview_project_artifact(
    db: Session,
    request: Request,
    project_id: str,
    path: str,
    *,
    task_id: str | None = None,
    dispatch_id: str | None = None,
    source_message_id: str | None = None,
    workstation_id: str | None = None,
):
    principal = None
    if request is not None and request.headers.get("authorization"):
        principal = require_project_read_access(db, request, project_id, action="collaboration.artifact.preview")
    else:
        try:
            principal = require_project_read_access(db, request, project_id, action="collaboration.artifact.preview")
        except AppError as exc:
            if exc.code != "UNAUTHORIZED":
                raise
    if principal is None:
        project = db.get(Project, str(project_id or "").strip())
        if project is None:
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
    artifact_path = _safe_artifact_text_path(path)
    artifact_relative_path = str(artifact_path.relative_to(_repo_root())).replace("\\", "/")
    if _artifact_preview_scope_requested(
        task_id=task_id,
        dispatch_id=dispatch_id,
        source_message_id=source_message_id,
        workstation_id=workstation_id,
    ):
        _assert_artifact_preview_scope(
            db,
            project_id=project_id,
            artifact_path=artifact_relative_path,
            task_id=task_id,
            dispatch_id=dispatch_id,
            source_message_id=source_message_id,
            workstation_id=workstation_id,
        )
    max_chars = 120_000
    content = artifact_path.read_text(encoding="utf-8", errors="replace")
    truncated = len(content) > max_chars
    if truncated:
        content = content[:max_chars].rstrip() + "\n\n[平台提示] 预览已截断，请在本机 artifact 文件中查看完整内容。"
    return ok(
        {
            "project_id": project_id,
            "path": artifact_relative_path,
            "name": artifact_path.name,
            "size_bytes": artifact_path.stat().st_size,
            "truncated": truncated,
            "content": content,
        }
    )


@router.post("/messages/preview")
def api_preview_message(payload: CollaborationMessageCreate, request: Request, db: Session = Depends(get_db)):
    principal = _require_real_human_principal(db, request)
    project_id = _collaboration_message_project_id(db, payload)
    resolve_project_write_principal(db, request, project_id, action="collaboration.message.preview")

    blockers: list[str] = []
    warnings: list[str] = []
    preview_notes: list[str] = ["这一步只生成预演，不会写入平台协作消息池。"]

    if payload.message_type in {"runner_command", "runner_ack", "runner_result"}:
        blockers.append("runner relay 消息必须走专用接口，不能从通用协作入口直接发送。")

    cleaned_body = str(payload.body or "").strip()
    if not cleaned_body:
        blockers.append("指令正文不能为空。")

    cleaned_recipient_id = str(payload.recipient_id or "").strip()
    cleaned_recipient_type = str(payload.recipient_type or "").strip()
    recipient_label: str | None = None
    if not cleaned_recipient_id:
        blockers.append("还没有选择目标线程或 NPC。")
    elif not cleaned_recipient_type:
        blockers.append("还没有指定目标类型。")
    else:
        try:
            recipient_label, _ = _resolve_collaboration_message_recipient_label(
                db,
                project_id=project_id,
                recipient_type=cleaned_recipient_type,
                recipient_id=cleaned_recipient_id,
            )
        except AppError:
            blockers.append("目标线程或电脑不存在，可能已经被删除或换了项目。")

    pending_target_message_count = 0
    recent_same_type_count = 0
    if cleaned_recipient_id and cleaned_recipient_type:
        target_messages = list(
            db.scalars(
                select(CollaborationMessage).where(
                    CollaborationMessage.project_id == project_id,
                    CollaborationMessage.recipient_type == cleaned_recipient_type,
                    CollaborationMessage.recipient_id == cleaned_recipient_id,
                )
            )
        )
        pending_target_message_count = sum(
            1
            for item in target_messages
            if str(item.status or "").strip().lower() not in {"completed", "failed", "done", "cancelled"}
        )
        recent_same_type_count = sum(
            1
            for item in target_messages
            if str(item.message_type or "").strip().lower() == str(payload.message_type or "").strip().lower()
        )
        if pending_target_message_count:
            warnings.append(f"这个目标当前还有 {pending_target_message_count} 条未收口的协作消息。")
        if recent_same_type_count:
            preview_notes.append(f"同类型历史消息 {recent_same_type_count} 条，可先核对回执后再决定是否继续派工。")

    if len(cleaned_body) < 20:
        warnings.append("这条指令比较短，建议把验收标准或回执要求写完整。")
    if not str(payload.title or "").strip():
        warnings.append("建议补一个标题，后续最终回复池和对话框会更容易追踪。")

    ready = not blockers
    preview_notes.append(
        f"目标：{recipient_label or cleaned_recipient_id or '未选择'} / 类型：{str(payload.message_type or 'comment_message').strip() or 'comment_message'}"
    )
    next_step = "可以正式登记到平台协作消息池。" if ready else "先处理预演阻塞，再正式登记。"
    preview_signature = _build_collaboration_message_preview_signature(
        payload,
        project_id=project_id,
        sender_id=str(principal.user_id or "").strip() or None,
    )

    return ok(
        CollaborationMessagePreviewRead(
            project_id=project_id,
            task_id=payload.task_id,
            approval_id=payload.approval_id,
            handoff_id=payload.handoff_id,
            requirement_id=payload.requirement_id,
            agent_id=payload.agent_id,
            message_type=str(payload.message_type or "comment_message").strip() or "comment_message",
            title=(str(payload.title or "").strip() or None),
            body=cleaned_body,
            sender_type="human",
            sender_id=str(principal.user_id or "").strip() or None,
            recipient_type=cleaned_recipient_type or None,
            recipient_id=cleaned_recipient_id or None,
            recipient_label=recipient_label,
            status=str(payload.status or "open").strip() or "open",
            ready=ready,
            preview_signature=preview_signature,
            pending_target_message_count=pending_target_message_count,
            recent_same_type_count=recent_same_type_count,
            blockers=blockers,
            warnings=warnings,
            preview_notes=preview_notes,
            next_step=next_step,
        ).model_dump(mode="json")
    )


@router.post("/messages")
def api_create_message(payload: CollaborationMessageCreate, request: Request, db: Session = Depends(get_db)):
    if payload.message_type in {"runner_command", "runner_ack", "runner_result"}:
        raise AppError("FORBIDDEN_MESSAGE_TYPE", "runner relay 消息必须走专用接口", status_code=403)
    project_id = _collaboration_message_project_id(db, payload)
    sender_type = (payload.sender_type or "").strip().lower()
    sender_id = (payload.sender_id or "").strip()
    recipient_type = (payload.recipient_type or "").strip().lower()
    recipient_id = (payload.recipient_id or "").strip()
    message_type = (payload.message_type or "").strip()
    header_workstation_id = read_identity_header(request, "x-workstation-id")
    workstation_peer_principal = False
    principal_user_id: str | None = None
    if (
        header_workstation_id
        and sender_type == "agent"
        and sender_id
        and recipient_type == "thread_workstation"
        and recipient_id
        and message_type in {"comment_message", "requirement_dispatch", "agent_command"}
    ):
        from app.modules.requirements.service import _resolve_seat

        header_seat = _resolve_seat(db, project_id, header_workstation_id)
        sender_seat = _resolve_seat(db, project_id, sender_id)
        if header_seat is None or sender_seat is None or header_seat.id != sender_seat.id:
            raise AppError(
                "PERMISSION_DENIED",
                "NPC 自主派单必须由当前项目里的正式发送 NPC 发起",
                status_code=403,
                details={"project_id": project_id, "sender_id": sender_id, "header_workstation_id": header_workstation_id},
            )
        _require_workstation_inbox_access(
            db,
            request,
            project_id,
            header_workstation_id,
            write=True,
            action="collaboration.peer_dispatch.create",
        )
        workstation_peer_principal = True
    else:
        principal = _require_real_human_principal(db, request)
        principal_user_id = str(principal.user_id or "").strip() or None
        resolve_project_write_principal(db, request, project_id, action="collaboration.message.create")
    if sender_type == "agent" and sender_id:
        cfg = get_project_collaboration_config(db, project_id)
        inner = cfg.get("collaboration_config", {}) if isinstance(cfg.get("collaboration_config"), dict) else {}
        seats = inner.get("thread_workstations") or []
        valid_ids = {str(s.get("id") or "") for s in seats} | {str(s.get("config_id") or "") for s in seats} | {str(s.get("row_id") or "") for s in seats}
        if sender_id in valid_ids:
            metadata = _collaboration_payload_extra_data(payload)
            if workstation_peer_principal:
                metadata.setdefault("origin", "agent_peer_dispatch")
                metadata.setdefault("actor_workstation_id", header_workstation_id)
            else:
                metadata.setdefault("origin", "human_proxy")
                metadata.setdefault("actor_user_id", principal_user_id)
            metadata.setdefault("claimed_sender_agent_id", sender_id)
            override = {"project_id": project_id, "metadata": metadata}
        else:
            if workstation_peer_principal:
                raise AppError(
                    "NPC_SENDER_NOT_FOUND",
                    "sender_id 必须是当前项目里的正式 seat，不能使用 session 或历史别名",
                    status_code=404,
                    details={"blocked_reason": "NPC_SENDER_NOT_FOUND"},
                )
            override = {"project_id": project_id, "sender_type": "human", "sender_id": principal.user_id}
    else:
        if workstation_peer_principal:
            raise AppError("FORBIDDEN_MESSAGE_TYPE", "NPC 工位身份只能发起 NPC 互派消息", status_code=403)
        override = {"project_id": project_id, "sender_type": "human", "sender_id": principal.user_id}

    metadata = _collaboration_payload_extra_data(payload)
    if _payload_card_kind(metadata) in {"boundary", "boundary-card", "dispatch-boundary", "pre-dispatch"}:
        metadata.setdefault("pre_dispatch_gate", True)
        metadata.setdefault("requires_human_review", True)
        metadata.setdefault("gate_policy", "boundary_card_before_dispatch")
        override["metadata"] = metadata
        override["status"] = "pending_review"

    # NPC 之间互派需求/消息：自动应用三级 review_policy + 跨工位强审
    final_sender_type = (override.get("sender_type") or sender_type or "").lower()
    final_sender_id = (override.get("sender_id") or sender_id or "").strip()
    if (
        final_sender_type == "agent"
        and final_sender_id
        and recipient_type == "thread_workstation"
        and recipient_id
        and (payload.message_type or "") in {"comment_message", "requirement_dispatch", "agent_command"}
    ):
        from app.modules.requirements.service import _resolve_seat, _resolve_review_for_dispatch
        upstream = _resolve_seat(db, project_id, final_sender_id)
        downstream = _resolve_seat(db, project_id, recipient_id)
        if upstream is None:
            create_audit_log(
                db,
                project_id=project_id,
                actor_type=final_sender_type or "agent",
                actor_id=final_sender_id or None,
                action="dispatch.blocked_history_alias",
                resource_type="collaboration_message",
                before={
                    "sender_id": final_sender_id,
                    "recipient_id": recipient_id,
                    "message_type": payload.message_type,
                },
                after={
                    "blocked_reason": "NPC_SENDER_NOT_FOUND",
                    "blocked_detail": "sender must resolve by formal seat id/config_id inside current project",
                },
                success=False,
                error_message="sender_id must be a formal seat id/config_id in the current project",
            )
            db.commit()
            raise AppError(
                "NPC_SENDER_NOT_FOUND",
                "sender_id 必须是当前项目里的正式 seat，不能使用 session 或历史别名",
                status_code=404,
                details={"blocked_reason": "NPC_SENDER_NOT_FOUND"},
            )
        if downstream is None:
            create_audit_log(
                db,
                project_id=project_id,
                actor_type=final_sender_type or "agent",
                actor_id=final_sender_id or None,
                action="dispatch.blocked_history_alias",
                resource_type="collaboration_message",
                before={
                    "sender_id": final_sender_id,
                    "recipient_id": recipient_id,
                    "message_type": payload.message_type,
                },
                after={
                    "blocked_reason": "NPC_RECIPIENT_NOT_FOUND",
                    "blocked_detail": "recipient must resolve by formal seat id/config_id inside current project",
                },
                success=False,
                error_message="recipient_id must be a formal seat id/config_id in the current project",
            )
            db.commit()
            raise AppError(
                "NPC_RECIPIENT_NOT_FOUND",
                "recipient_id 必须是当前项目里的正式 seat，不能使用 session 或历史别名",
                status_code=404,
                details={"blocked_reason": "NPC_RECIPIENT_NOT_FOUND"},
            )
        metadata = dict(override.get("metadata") or _collaboration_payload_extra_data(payload))
        source_message_id = str(
            metadata.get("source_message_id")
            or metadata.get("sourceMessageId")
            or metadata.get("linked_message_id")
            or metadata.get("linkedMessageId")
            or ""
        ).strip() or None
        metadata = _ensure_peer_delegation_context(
            metadata,
            project_id=project_id,
            delegated_by_user_id=_resolve_delegated_by_user_id_for_peer_dispatch(
                db,
                project_id=project_id,
                source_message_id=source_message_id,
                fallback_user_id=principal_user_id,
            ),
            delegated_via_seat_id=final_sender_id,
            target_seat_id=recipient_id,
            source_message_id=source_message_id,
        )
        metadata.setdefault("authoritative_sender_seat_id", final_sender_id)
        metadata.setdefault("authoritative_target_seat_id", recipient_id)
        metadata.setdefault("historical_alias_non_authoritative", False)
        override["metadata"] = metadata
        is_cross = _seat_logical_workstation_key(upstream) != _seat_logical_workstation_key(downstream)
        via_lead_note = ""
        if is_cross:
            cfg_full = get_project_collaboration_config(db, project_id)
            inner_cfg = cfg_full.get("collaboration_config", {}) if isinstance(cfg_full.get("collaboration_config"), dict) else {}
            profiles = inner_cfg.get("workstation_profiles") if isinstance(inner_cfg.get("workstation_profiles"), dict) else {}
            lead_ref = _resolve_logical_workstation_lead_ref(db, project_id, downstream, profiles)
            if lead_ref and lead_ref not in {downstream.id, downstream.config_id, downstream.name}:
                new_lead_seat = _resolve_seat(db, project_id, lead_ref)
                if new_lead_seat is not None:
                    original_target_name = getattr(downstream, "name", "")
                    original_target_id = recipient_id
                    override["recipient_id"] = new_lead_seat.id
                    recipient_id = new_lead_seat.id
                    downstream = new_lead_seat
                    via_lead_note = f"经工位长 {getattr(new_lead_seat, 'name', '')} 转交（原始目标 NPC: {original_target_name} / {original_target_id}）"
        review = _resolve_review_for_dispatch(db, upstream, downstream)
        hardware_risk_keyword = _detect_hardware_review_risk(payload.body or "")
        if hardware_risk_keyword:
            review = {
                **review,
                "requires_review": True,
                "source": "hardware_risk",
                "policy": "force",
                "risk_keyword": hardware_risk_keyword,
            }
        requested_status = (override.get("status") or payload.status or "").strip() or "open"
        new_status = "pending_review" if review["requires_review"] else (
            requested_status if requested_status in {"queued", "pending_review", "open"} else "queued"
        )
        if not review["requires_review"] and new_status == "pending_review":
            new_status = "queued"
        override["status"] = new_status
        review_label = "需要人工确认" if review["requires_review"] else "同工位免审" if not is_cross else "按项目规则免审"
        route_line = (
            f"\n\n[协作路由] 跨工位：{'是' if is_cross else '否'}；"
            f"审核：{review_label}；"
            f"上游 NPC: {getattr(upstream, 'name', '')}；下游 NPC: {getattr(downstream, 'name', '')}"
            f"；上游工位: {_seat_logical_workstation_key(upstream) or '未归属'}；下游工位: {_seat_logical_workstation_key(downstream) or '未归属'}"
        )
        if hardware_risk_keyword:
            route_line += f"；硬件风险: {hardware_risk_keyword}"
        if via_lead_note:
            route_line += f"；{via_lead_note}"
        body_text = str(payload.body or "")
        if "[路由]" not in body_text and "[协作路由]" not in body_text:
            override["body"] = body_text + route_line

    item = create_collaboration_message(db, payload.model_copy(update=override))
    if (item.status or "") == "pending_review" and ("审核：免" in str(item.body or "") or "审核：同工位免审" in str(item.body or "")):
        item.status = "queued"
        db.add(item)
        db.commit()
        db.refresh(item)
    item_metadata = _collaboration_payload_extra_data(payload)
    if (
        (item.sender_type or "").lower() == "agent"
        and item.sender_id
        and (item.recipient_type or "").lower() == "thread_workstation"
        and item.recipient_id
        and isinstance(item.extra_data, dict)
        and isinstance(item.extra_data.get("delegation_context"), dict)
    ):
        create_audit_log(
            db,
            project_id=project_id,
            actor_type="agent",
            actor_id=item.sender_id,
            action="collaboration.delegation.peer_dispatch.created",
            resource_type="collaboration_message",
            resource_id=item.id,
            before={
                "origin": item_metadata.get("origin"),
                "sender_id": item.sender_id,
                "recipient_id": item.recipient_id,
            },
            after={
                "delegation_context": item.extra_data.get("delegation_context"),
                "status": item.status,
            },
            success=True,
        )
        db.commit()
        db.refresh(item)
    return ok(CollaborationMessageRead.model_validate(item).model_dump(mode="json"))


@router.patch("/messages/{message_id}")
def api_update_message(
    message_id: str,
    payload: CollaborationMessageUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    principal = _require_real_human_principal(db, request)
    existing = get_collaboration_message_or_404(db, message_id)
    project_id = _collaboration_message_scope_project_id(
        db,
        project_id=existing.project_id,
        task_id=existing.task_id,
        approval_id=existing.approval_id,
        handoff_id=existing.handoff_id,
        requirement_id=existing.requirement_id,
        agent_id=existing.agent_id,
    )
    resolve_project_write_principal(db, request, project_id, action="collaboration.message.update")
    item = update_collaboration_message(db, message_id, payload, actor_type="human", actor_id=principal.user_id)
    return ok(CollaborationMessageRead.model_validate(item).model_dump(mode="json"))


@router.post("/messages/{message_id}/review/approve")
def api_review_approve_message(
    message_id: str,
    request: Request,
    payload: MessageReviewActionRequest | None = None,
    db: Session = Depends(get_db),
):
    """通过待审消息：消息 status pending_review → queued；联动 requirement.status blocked → queued。"""
    principal = _require_real_human_principal(db, request)
    existing = get_collaboration_message_or_404(db, message_id)
    project_id = _collaboration_message_scope_project_id(
        db,
        project_id=existing.project_id,
        task_id=existing.task_id,
        approval_id=existing.approval_id,
        handoff_id=existing.handoff_id,
        requirement_id=existing.requirement_id,
        agent_id=existing.agent_id,
    )
    resolve_project_write_principal(db, request, project_id, require_privileged=False, action="collaboration.message.review.approve")
    if (existing.status or "") != "pending_review":
        raise AppError("MESSAGE_NOT_PENDING_REVIEW", f"消息当前状态={existing.status}，不在 pending_review", status_code=409)
    # 用 WHERE status='pending_review' 守护并发：只有第一个并发请求会改成 queued，后到的 rowcount=0
    from app.db.models.collaboration_message import CollaborationMessage
    rowcount = db.query(CollaborationMessage).filter(
        CollaborationMessage.id == existing.id,
        CollaborationMessage.status == "pending_review",
    ).update({"status": "queued"}, synchronize_session=False)
    if rowcount == 0:
        db.rollback()
        raise AppError("MESSAGE_NOT_PENDING_REVIEW", "消息已被其他人审批，请刷新", status_code=409)
    if existing.requirement_id:
        from app.db.models.requirement import Requirement
        req = db.get(Requirement, existing.requirement_id)
        if req is not None and (req.status or "") in {"blocked", "pending_review"}:
            req.status = "queued"
            db.add(req)
    runner_command = _runner_command_from_robotics_review(existing)
    if runner_command is not None:
        create_runner_command(db, project_id, sender_id=principal.user_id or "", payload=runner_command)
    remember_result = None
    remember_policy = str(getattr(payload, "remember_pair_policy", "") or "").strip().lower()
    if remember_policy in {"skip", "force"}:
        remember_result = _set_npc_pair_review_policy(
            db,
            project_id,
            upstream_seat_id=existing.sender_id or "",
            downstream_seat_id=existing.recipient_id or "",
            policy=remember_policy,
            actor_id=principal.user_id,
            reason=(payload.reason if payload else None) or f"set while approving message {existing.id}",
        )
    db.refresh(existing)
    autostart_workstation_command_after_review(db, existing)
    db.commit()
    db.refresh(existing)
    data = CollaborationMessageRead.model_validate(existing).model_dump(mode="json")
    if remember_result is not None:
        data["review_pair_policy"] = remember_result
    return ok(data)


@router.post("/messages/{message_id}/review/reject")
def api_review_reject_message(
    message_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """打回待审消息：消息 status pending_review → cancelled；联动 requirement.status blocked → cancelled。"""
    principal = _require_real_human_principal(db, request)
    existing = get_collaboration_message_or_404(db, message_id)
    project_id = _collaboration_message_scope_project_id(
        db,
        project_id=existing.project_id,
        task_id=existing.task_id,
        approval_id=existing.approval_id,
        handoff_id=existing.handoff_id,
        requirement_id=existing.requirement_id,
        agent_id=existing.agent_id,
    )
    resolve_project_write_principal(db, request, project_id, require_privileged=False, action="collaboration.message.review.reject")
    if (existing.status or "") != "pending_review":
        raise AppError("MESSAGE_NOT_PENDING_REVIEW", f"消息当前状态={existing.status}，不在 pending_review", status_code=409)
    from app.db.models.collaboration_message import CollaborationMessage
    rowcount = db.query(CollaborationMessage).filter(
        CollaborationMessage.id == existing.id,
        CollaborationMessage.status == "pending_review",
    ).update({"status": "cancelled"}, synchronize_session=False)
    if rowcount == 0:
        db.rollback()
        raise AppError("MESSAGE_NOT_PENDING_REVIEW", "消息已被其他人审批，请刷新", status_code=409)
    if existing.requirement_id:
        from app.db.models.requirement import Requirement
        req = db.get(Requirement, existing.requirement_id)
        if req is not None and (req.status or "") in {"blocked", "pending_review"}:
            req.status = "cancelled"
            db.add(req)
    db.commit()
    db.refresh(existing)
    return ok(CollaborationMessageRead.model_validate(existing).model_dump(mode="json"))


@router.post("/projects/{project_id}/runner-commands")
def api_create_runner_command(
    project_id: str,
    payload: RunnerRelayCommandCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    principal = _require_real_human_principal(db, request)
    resolve_project_write_principal(db, request, project_id, require_privileged=True, action="collaboration.runner_command.create")
    item = create_runner_command(db, project_id, sender_id=principal.user_id or "", payload=payload)
    return ok(RunnerRelayMessageRead.model_validate(item).model_dump(mode="json"))


class BroadcastRequest(BaseModel):
    scope: str = Field(..., description='"all" 或 "workstation:<computer_node_id>"')
    title: str | None = None
    body: str
    message_type: str = Field(default="comment_message")


def _is_npc_seat(record: dict) -> bool:
    if not isinstance(record, dict):
        return False
    seat_type = ""
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    extra_data = record.get("extra_data") if isinstance(record.get("extra_data"), dict) else {}
    for source in (metadata, extra_data, record):
        candidate = source.get("seat_type") if isinstance(source, dict) else None
        if candidate:
            seat_type = str(candidate).strip().lower()
            break
    return seat_type in {"codex", "npc"}


def _resolve_broadcast_targets(config: dict, scope: str) -> tuple[list[dict], str]:
    workstations = config.get("collaboration_config", {}) if isinstance(config.get("collaboration_config"), dict) else config
    raw = (
        workstations.get("thread_workstations")
        or workstations.get("threadWorkstations")
        or workstations.get("workstations")
        or []
    )
    seats = [item for item in raw if isinstance(item, dict) and _is_npc_seat(item)]
    scope = (scope or "all").strip()
    if scope == "all":
        return seats, "全员"
    if scope.startswith("workstation:"):
        node_id = scope.split(":", 1)[1].strip()
        if not node_id:
            return [], "未指定工位"
        targets = [
            seat
            for seat in seats
            if str(seat.get("computer_node_id") or seat.get("computerNodeId") or "").strip() == node_id
        ]
        return targets, f"工位 {node_id}"
    return [], "未知 scope"


def _broadcast_target_summary(seat: dict) -> dict:
    return {
        "id": str(seat.get("id") or seat.get("config_id") or seat.get("row_id") or ""),
        "name": str(seat.get("name") or seat.get("title") or "未命名 NPC"),
        "computer_node_id": str(seat.get("computer_node_id") or seat.get("computerNodeId") or ""),
        "provider_label": str(seat.get("provider_label") or seat.get("providerLabel") or seat.get("provider_id") or ""),
        "responsibility": str(seat.get("responsibility") or "")[:60],
    }


def _normalize_review_policy(value: object) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"force", "always", "on"}:
        return "force"
    if raw in {"skip", "never", "off"}:
        return "skip"
    if raw in {"inherit", "default", ""}:
        return "inherit"
    if raw in {"cross_workstation_only", "cross"}:
        return "cross_workstation_only"
    return "inherit"


def _seat_review_policy(seat: dict) -> str:
    metadata = seat.get("metadata") if isinstance(seat.get("metadata"), dict) else {}
    return _normalize_review_policy(
        seat.get("review_policy")
        or seat.get("reviewPolicy")
        or metadata.get("review_policy")
        or metadata.get("reviewPolicy")
    )


def _workstation_review_policy(config: dict, workstation_key: str, node_id: str = "") -> str:
    profiles = config.get("workstation_profiles") if isinstance(config.get("workstation_profiles"), dict) else {}
    profile = profiles.get(workstation_key) if isinstance(profiles, dict) and workstation_key else None
    if not isinstance(profile, dict) and isinstance(profiles, dict) and node_id and node_id != workstation_key:
        profile = profiles.get(node_id)
    if not isinstance(profile, dict):
        return "inherit"
    return _normalize_review_policy(profile.get("review_policy") or profile.get("reviewPolicy"))


def _project_default_review_policy(config: dict) -> str:
    rp = config.get("review_policy") if isinstance(config.get("review_policy"), dict) else None
    if isinstance(rp, dict):
        return _normalize_review_policy(rp.get("default") or rp.get("project_default"))
    return _normalize_review_policy(config.get("review_policy_default"))


def resolve_seat_review(
    config: dict,
    seat: dict,
    *,
    is_cross_workstation: bool = False,
) -> dict:
    """合并三层 review policy，返回是否要走人审 + 来源。"""
    seat_id = str(seat.get("id") or seat.get("config_id") or seat.get("row_id") or "")
    workstation_key = str(seat.get("workstation_id") or seat.get("workstationId") or "").strip()
    node_id = str(seat.get("computer_node_id") or seat.get("computerNodeId") or "")
    profile_key = workstation_key or node_id
    seat_pol = _seat_review_policy(seat)
    if seat_pol in {"force", "skip"}:
        return {
            "requires_review": seat_pol == "force",
            "source": "npc",
            "seat_id": seat_id,
            "policy": seat_pol,
        }
    ws_pol = _workstation_review_policy(config, profile_key, node_id) if profile_key else "inherit"
    if ws_pol in {"force", "skip"}:
        return {
            "requires_review": ws_pol == "force",
            "source": "workstation",
            "seat_id": seat_id,
            "policy": ws_pol,
        }
    project_pol = _project_default_review_policy(config) or "cross_workstation_only"
    if project_pol == "force":
        return {"requires_review": True, "source": "project", "seat_id": seat_id, "policy": project_pol}
    if project_pol == "skip":
        return {"requires_review": False, "source": "project", "seat_id": seat_id, "policy": project_pol}
    return {
        "requires_review": bool(is_cross_workstation),
        "source": "project_default_cross_only",
        "seat_id": seat_id,
        "policy": project_pol,
    }


def _estimate_broadcast_tokens(body: str, target_count: int) -> int:
    body_chars = len(body or "")
    per_target = max(160, body_chars + 80)
    return per_target * max(1, target_count)


@router.post("/projects/{project_id}/broadcast/preview")
def api_broadcast_preview(
    project_id: str,
    payload: BroadcastRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_real_human_principal(db, request)
    resolve_project_write_principal(db, request, project_id, action="collaboration.broadcast.preview")
    config = get_project_collaboration_config(db, project_id)
    targets, scope_label = _resolve_broadcast_targets(config, payload.scope)
    body = (payload.body or "").strip()
    blockers: list[str] = []
    warnings: list[str] = []
    if not body:
        blockers.append("广播内容不能为空。")
    if len(body) < 30:
        warnings.append("广播内容偏短，建议补全验收标准 / 回执要求。")
    if not targets:
        blockers.append(f"{scope_label} 没有可派发的 NPC。")
    if len(targets) > 20:
        warnings.append(f"将一次性派发给 {len(targets)} 个 NPC，建议先在小范围验证。")
    estimated = _estimate_broadcast_tokens(body, len(targets))
    config_inner = config.get("collaboration_config", {}) if isinstance(config.get("collaboration_config"), dict) else config
    scope_str = (payload.scope or "all").strip()
    is_cross_workstation_scope = scope_str == "all" and len({
        str(seat.get("workstation_id") or seat.get("workstationId") or seat.get("computer_node_id") or seat.get("computerNodeId") or "")
        for seat in targets
    }) > 1
    review_decisions = [
        resolve_seat_review(config_inner, seat, is_cross_workstation=is_cross_workstation_scope)
        for seat in targets
    ]
    review_force_count = sum(1 for d in review_decisions if d["requires_review"])
    requires_human_review = (
        review_force_count > 0
        or len(targets) >= 5
        or len(body) >= 1500
    )
    return ok(
        {
            "scope": payload.scope,
            "scope_label": scope_label,
            "target_count": len(targets),
            "targets": [_broadcast_target_summary(seat) for seat in targets],
            "estimated_tokens": estimated,
            "requires_human_review": requires_human_review,
            "review_decisions": review_decisions,
            "review_force_count": review_force_count,
            "blockers": blockers,
            "warnings": warnings,
            "ready": not blockers,
        }
    )


@router.post("/projects/{project_id}/broadcast/commit")
def api_broadcast_commit(
    project_id: str,
    payload: BroadcastRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    principal = _require_real_human_principal(db, request)
    resolve_project_write_principal(db, request, project_id, action="collaboration.broadcast.commit")
    config = get_project_collaboration_config(db, project_id)
    targets, scope_label = _resolve_broadcast_targets(config, payload.scope)
    body = (payload.body or "").strip()
    if not body:
        raise AppError("BAD_REQUEST", "广播内容不能为空", status_code=400)
    if not targets:
        raise AppError("BAD_REQUEST", f"{scope_label} 没有可派发的 NPC", status_code=400)
    broadcast_id = uuid.uuid4().hex
    title = (payload.title or "").strip() or f"{scope_label} 广播"
    message_type = (payload.message_type or "comment_message").strip() or "comment_message"
    if message_type in {"runner_command", "runner_ack", "runner_result"}:
        raise AppError("FORBIDDEN_MESSAGE_TYPE", "广播不支持 runner relay 类型", status_code=403)
    created: list[str] = []
    for seat in targets:
        seat_id = str(seat.get("id") or seat.get("config_id") or seat.get("row_id") or "").strip()
        if not seat_id:
            continue
        message_payload = CollaborationMessageCreate(
            project_id=project_id,
            message_type=message_type,
            title=title,
            body=body,
            sender_type="human",
            sender_id=principal.user_id,
            recipient_type="thread_workstation",
            recipient_id=seat_id,
            status="open",
        )
        item = create_collaboration_message(db, message_payload, dispatch_id=broadcast_id)
        created.append(item.id)
    return ok(
        {
            "broadcast_id": broadcast_id,
            "scope": payload.scope,
            "scope_label": scope_label,
            "title": title,
            "message_type": message_type,
            "target_count": len(targets),
            "created_message_ids": created,
        }
    )
