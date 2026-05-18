from __future__ import annotations

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.errors import AppError
from app.db.models.collaboration_message import CollaborationMessage
from app.db.models.project_collaboration import ProjectThreadWorkstation
from app.db.models.requirement import Requirement, RequirementMessage
from app.db.models.task import Task
from app.modules.audit.service import create_audit_log
from app.modules.collaboration.schemas import CollaborationMessageCreate
from app.modules.collaboration.service import create_message as create_collaboration_message

from . import repo
from .schemas import (
    NeedRouteRequest,
    RequirementActionRequest,
    RequirementCreate,
    RequirementDispatchRequest,
    RequirementFinalReplyRequest,
    RequirementPromoteRequest,
    RequirementReplyCreate,
    RequirementRouteRequest,
    StructuredNeedCreate,
    RequirementUpdate,
)

MAINTENANCE_TEMPLATE_TITLES = {
    "平台主链自检",
    "复查电脑与线程扫描",
    "人工确认平台风险点",
}
MAINTENANCE_TEMPLATE_TITLE_ALIASES = {
    "骞冲彴涓婚摼鑷": "平台主链自检",
    "澶嶆煡鐢佃剳涓庣嚎绋嬫壂鎻": "复查电脑与线程扫描",
    "澶嶆煡鐢佃剳涓庣嚎绋嬫壂鎻?": "复查电脑与线程扫描",
    "浜哄伐纭骞冲彴椋庨櫓鐐": "人工确认平台风险点",
    "浜哄伐纭骞冲彴椋庨櫓鐐?": "人工确认平台风险点",
}
MAINTENANCE_TEMPLATE_TITLE_MATCHES = MAINTENANCE_TEMPLATE_TITLES | set(MAINTENANCE_TEMPLATE_TITLE_ALIASES.keys())
FOLLOW_UP_SUFFIX = "后续复查"
OPEN_REQUIREMENT_STATUSES = {"waiting_response", "queued", "routed", "in_progress", "answered"}
TASK_SYNC_STATUS_PRIORITY = {
    "in_progress": 50,
    "answered": 40,
    "queued": 30,
    "routed": 20,
    "waiting_response": 10,
}


def _normalize_maintenance_template_title(value: str | None) -> str:
    cleaned = str(value or "").strip()
    if cleaned in MAINTENANCE_TEMPLATE_TITLES:
        return cleaned
    return MAINTENANCE_TEMPLATE_TITLE_ALIASES.get(cleaned, cleaned)


def _validate_requirement_dispatch_target(
    db: Session,
    requirement: Requirement,
    *,
    target_type: str,
    target_id: str,
) -> None:
    cleaned = target_id.strip()
    if not cleaned:
        raise AppError("VALIDATION_ERROR", "dispatch target_id is required", status_code=422)
    if target_type == "human":
        return
    stmt = select(ProjectThreadWorkstation).where(ProjectThreadWorkstation.project_id == requirement.project_id)
    workstations = list(db.scalars(stmt))
    if target_type == "workstation":
        exists = any(cleaned in {item.id, item.config_id} for item in workstations)
    else:
        exists = any(cleaned == (item.agent_id or "") for item in workstations)
    if not exists:
        raise AppError(
            "TARGET_NOT_FOUND",
            f"dispatch target {target_type}:{cleaned} is not bound to this project via formal seat id/config_id",
            status_code=404,
        )


def list_requirements(db: Session, project_ids: list[str] | None = None):
    return repo.list_requirements(db, project_ids=project_ids)


def get_requirement_or_404(db: Session, requirement_id: str):
    requirement = repo.get_requirement(db, requirement_id)
    if requirement is None:
        raise AppError("NOT_FOUND", "需求单不存在", status_code=404)
    return requirement


def _find_existing_follow_up_requirement(db: Session, requirement: Requirement) -> Requirement | None:
    normalized_title = _normalize_maintenance_template_title(requirement.title)
    follow_up_title = f"{normalized_title} {FOLLOW_UP_SUFFIX}"
    stmt = (
        select(Requirement)
        .where(Requirement.follow_up_from_requirement_id == requirement.id)
        .order_by(Requirement.updated_at.desc(), Requirement.created_at.desc())
    )
    existing = db.scalar(stmt)
    if existing is not None:
        return existing

    fallback_stmt = (
        select(Requirement)
        .where(
            Requirement.project_id == requirement.project_id,
            Requirement.task_id == requirement.task_id,
            Requirement.title == follow_up_title,
            Requirement.follow_up_from_requirement_id.is_(None),
            Requirement.status.in_(sorted(OPEN_REQUIREMENT_STATUSES)),
        )
        .order_by(Requirement.updated_at.desc(), Requirement.created_at.desc())
    )
    fallback = db.scalar(fallback_stmt)
    if fallback is not None and fallback.follow_up_from_requirement_id is None:
        fallback.follow_up_from_requirement_id = requirement.id
        db.add(fallback)
        db.flush()
    return fallback


def _has_open_follow_up_requirement(db: Session, requirement: Requirement) -> bool:
    return _find_existing_follow_up_requirement(db, requirement) is not None


def _follow_up_has_dispatch_message(db: Session, requirement_id: str) -> bool:
    stmt = select(CollaborationMessage.id).where(
        CollaborationMessage.requirement_id == requirement_id,
        CollaborationMessage.message_type == "requirement_dispatch",
    )
    return db.scalar(stmt.limit(1)) is not None


def _collaboration_message_by_dedupe_key(db: Session, dedupe_key: str | None) -> CollaborationMessage | None:
    cleaned = str(dedupe_key or "").strip()
    if not cleaned:
        return None
    stmt = (
        select(CollaborationMessage)
        .where(CollaborationMessage.dedupe_key == cleaned)
        .order_by(CollaborationMessage.updated_at.desc(), CollaborationMessage.created_at.desc())
    )
    return db.scalar(stmt)


def _auto_final_reply_dedupe_key(requirement_id: str, status: str) -> str:
    normalized_status = str(status or "").strip().lower() or "answered"
    return f"auto_final_reply:{requirement_id}:{normalized_status}"


def _auto_progress_ack_dedupe_key(requirement_id: str) -> str:
    return f"auto_progress_ack:{requirement_id}"


def _is_progress_ack_message(message: CollaborationMessage) -> bool:
    message_type = str(message.message_type or "").strip().lower()
    status = str(message.status or "").strip().lower()
    if message_type == "requirement_progress_ack":
        return True
    return message_type == "requirement_final_reply" and status == "in_progress"


def _existing_requirement_reply_for_final_status(
    db: Session,
    requirement_id: str,
    *,
    status: str,
    sender_type: str | None,
    sender_id: str | None,
) -> RequirementMessage | None:
    normalized_status = str(status or "").strip().lower()
    normalized_sender_type = str(sender_type or "").strip().lower()
    normalized_sender_id = str(sender_id or "").strip()
    stmt = (
        select(RequirementMessage)
        .where(
            RequirementMessage.requirement_id == requirement_id,
            RequirementMessage.status_after_reply == normalized_status,
        )
        .order_by(RequirementMessage.created_at.desc())
    )
    replies = list(db.scalars(stmt))
    if not replies:
        return None
    exact = next(
        (
            reply
            for reply in replies
            if str(reply.sender_type or "").strip().lower() == normalized_sender_type
            and str(reply.sender_id or "").strip() == normalized_sender_id
        ),
        None,
    )
    return exact or replies[0]


def _existing_final_reply_result(
    db: Session,
    requirement_id: str,
    *,
    dedupe_key: str | None,
    payload: RequirementFinalReplyRequest,
) -> dict[str, object] | None:
    existing_message = _collaboration_message_by_dedupe_key(db, dedupe_key)
    if existing_message is None:
        return None
    existing_reply = _existing_requirement_reply_for_final_status(
        db,
        requirement_id,
        status=payload.status,
        sender_type=payload.sender_type,
        sender_id=payload.sender_id,
    )
    if existing_reply is None:
        raise AppError(
            "INCONSISTENT_STATE",
            "existing final reply message is missing requirement reply row",
            status_code=409,
    )
    return {"reply": existing_reply, "message": existing_message}


def _existing_progress_ack_result(
    db: Session,
    requirement_id: str,
    *,
    dedupe_key: str | None,
    payload: RequirementFinalReplyRequest,
) -> dict[str, object] | None:
    existing_message = _collaboration_message_by_dedupe_key(db, dedupe_key)
    if existing_message is None:
        return None
    existing_reply = _existing_requirement_reply_for_final_status(
        db,
        requirement_id,
        status="in_progress",
        sender_type=payload.sender_type,
        sender_id=payload.sender_id,
    )
    if existing_reply is None:
        raise AppError(
            "INCONSISTENT_STATE",
            "existing progress ack message is missing requirement reply row",
            status_code=409,
        )
    return {"reply": existing_reply, "message": existing_message}


def _maybe_create_follow_up_requirement(
    db: Session,
    requirement: Requirement,
    *,
    actor_id: str,
) -> tuple[Requirement | None, bool]:
    title = _normalize_maintenance_template_title(requirement.title)
    if title not in MAINTENANCE_TEMPLATE_TITLES:
        return None, False
    existing = _find_existing_follow_up_requirement(db, requirement)
    if existing is not None:
        return existing, False

    try:
        created = repo.create_requirement(
            db,
            RequirementCreate(
                project_id=requirement.project_id,
                task_id=requirement.task_id,
                title=f"{title} {FOLLOW_UP_SUFFIX}",
                requirement_type=requirement.requirement_type,
                module=requirement.module,
                priority=requirement.priority,
                status="waiting_response",
                from_agent=actor_id,
                to_agent=requirement.to_agent,
                context_summary=f"{title} 已收到完成回执，请继续做一轮后续复查，并给最小回执。",
                expected_output="给一句话最小回执，说明后续复查结果，以及是否还需要继续处理。",
                related_files=list(requirement.related_files or []),
                max_response_tokens=requirement.max_response_tokens,
                opening_message=f"{title} 已完成一轮，现自动续推到后续复查，请继续检查并回最小结果。",
            ),
            extra_fields={"follow_up_from_requirement_id": requirement.id},
        )
        return created, True
    except IntegrityError:
        db.rollback()
        existing = _find_existing_follow_up_requirement(db, requirement)
        if existing is not None:
            return existing, False
        raise


def _auto_dispatch_follow_up_requirement(
    db: Session,
    requirement: Requirement,
    *,
    workstation_id: str | None,
    agent_id: str | None,
    actor_id: str,
) -> dict[str, object] | None:
    target_type: str | None = None
    target_id: str | None = None
    cleaned_workstation_id = str(workstation_id or "").strip()
    cleaned_agent_id = str(agent_id or "").strip()

    if cleaned_workstation_id:
        target_type = "workstation"
        target_id = cleaned_workstation_id
    elif cleaned_agent_id:
        target_type = "agent"
        target_id = cleaned_agent_id

    if not target_type or not target_id:
        return None

    result = dispatch_requirement(
        db,
        requirement.id,
        RequirementDispatchRequest(
            actor_type="agent",
            actor_id=actor_id,
            target_type=target_type,
            target_id=target_id,
            note="auto-dispatch follow-up from task execution",
            status="queued",
            title=requirement.title,
            body=requirement.expected_output or requirement.context_summary or requirement.title,
        ),
        dedupe_key=f"auto_follow_up_dispatch:{requirement.id}",
    )
    return {
        "requirement": result["requirement"],
        "message": result["message"],
        "target_type": target_type,
        "target_id": target_id,
    }


def _append_follow_up_affected(
    affected: list[dict[str, str]],
    follow_up_result: dict[str, object] | None,
) -> bool:
    if follow_up_result is None:
        return False
    follow_up = follow_up_result["requirement"]
    if bool(follow_up_result.get("created")):
        affected.append(
            {
                "requirement_id": follow_up.id,
                "title": follow_up.title,
                "action": "follow_up",
                "message_id": "",
            }
        )
    follow_up_dispatch = follow_up_result["dispatch"]
    if follow_up_dispatch is not None:
        affected.append(
            {
                "requirement_id": follow_up.id,
                "title": follow_up.title,
                "action": "follow_up_dispatch",
                "message_id": follow_up_dispatch["message"].id,
            }
        )
    return True


def _maybe_queue_follow_up_requirement(
    db: Session,
    requirement: Requirement,
    *,
    workstation_id: str | None,
    agent_id: str | None,
    actor_id: str,
) -> dict[str, object] | None:
    follow_up, created = _maybe_create_follow_up_requirement(db, requirement, actor_id=actor_id)
    if follow_up is None:
        return None
    follow_up_dispatch = None
    if created or not _follow_up_has_dispatch_message(db, follow_up.id):
        follow_up_dispatch = _auto_dispatch_follow_up_requirement(
            db,
            follow_up,
            workstation_id=workstation_id,
            agent_id=agent_id,
            actor_id=actor_id,
        )
    return {
        "requirement": follow_up,
        "dispatch": follow_up_dispatch,
        "created": created,
    }


def _workstation_dispatch_target_id(workstation: ProjectThreadWorkstation) -> str:
    return str(workstation.config_id or workstation.id).strip()


def _resolve_seat(db: Session, project_id: str | None, seat_ref: str | None) -> ProjectThreadWorkstation | None:
    """按正式 seat 标识解析 seat，仅允许项目内 id/config_id。"""
    cleaned = str(seat_ref or "").strip()
    if not cleaned or not project_id:
        return None
    stmt = select(ProjectThreadWorkstation).where(ProjectThreadWorkstation.project_id == project_id)
    for seat in db.scalars(stmt):
        if cleaned in {seat.id, seat.config_id}:
            return seat
    return None


def _seat_review_policy(seat: ProjectThreadWorkstation) -> str:
    extra = seat.extra_data if isinstance(getattr(seat, "extra_data", None), dict) else {}
    val = (extra or {}).get("review_policy") or (extra or {}).get("reviewPolicy") or ""
    val = str(val).strip().lower()
    if val in {"force", "always", "on"}: return "force"
    if val in {"skip", "never", "off"}: return "skip"
    return "inherit"


def _project_collab_config(db: Session, project_id: str | None) -> dict:
    if not project_id:
        return {}
    from app.modules.projects.service import get_project_config  # local import to avoid cycle
    try:
        cfg = get_project_config(db, project_id).get("collaboration_config")
    except Exception:
        cfg = None
    return cfg if isinstance(cfg, dict) else {}


def _review_pair_key(
    upstream_seat: ProjectThreadWorkstation | None,
    downstream_seat: ProjectThreadWorkstation | None,
) -> str:
    if upstream_seat is None or downstream_seat is None:
        return ""
    upstream_id = str(getattr(upstream_seat, "id", "") or "").strip()
    downstream_id = str(getattr(downstream_seat, "id", "") or "").strip()
    if not upstream_id or not downstream_id:
        return ""
    return f"{upstream_id}->{downstream_id}"


def _resolve_pair_review_rule(
    cfg: dict,
    upstream_seat: ProjectThreadWorkstation | None,
    downstream_seat: ProjectThreadWorkstation | None,
) -> tuple[str, dict] | None:
    key = _review_pair_key(upstream_seat, downstream_seat)
    if not key:
        return None
    rp = cfg.get("review_policy") if isinstance(cfg.get("review_policy"), dict) else {}
    pair_rules = rp.get("npc_pair_rules") if isinstance(rp, dict) and isinstance(rp.get("npc_pair_rules"), dict) else {}
    rule = pair_rules.get(key)
    if not isinstance(rule, dict):
        return None
    policy = str(rule.get("policy") or "").strip().lower()
    if policy in {"force", "always", "on"}:
        return "force", rule
    if policy in {"skip", "never", "off"}:
        return "skip", rule
    return None


def _resolve_review_for_dispatch(
    db: Session,
    upstream_seat: ProjectThreadWorkstation | None,
    downstream_seat: ProjectThreadWorkstation,
) -> dict:
    """review policy：目标 NPC 强审 > NPC 关系 > NPC 免审 > 工位 > 项目 default。"""
    seat_pol = _seat_review_policy(downstream_seat)
    if seat_pol == "force":
        return {"requires_review": True, "source": "npc", "policy": seat_pol}
    cfg = _project_collab_config(db, downstream_seat.project_id)
    pair_rule = _resolve_pair_review_rule(cfg, upstream_seat, downstream_seat)
    if pair_rule is not None:
        pair_policy, rule = pair_rule
        return {
            "requires_review": pair_policy == "force",
            "source": "npc_pair",
            "policy": pair_policy,
            "pair_key": _review_pair_key(upstream_seat, downstream_seat),
            "rule": rule,
        }
    if seat_pol == "skip":
        return {"requires_review": False, "source": "npc", "policy": seat_pol}
    profiles = cfg.get("workstation_profiles") if isinstance(cfg.get("workstation_profiles"), dict) else {}
    ws_key = _seat_workstation_key(downstream_seat)
    profile = profiles.get(ws_key) if isinstance(profiles, dict) and ws_key else None
    if profile is None and isinstance(profiles, dict):
        # legacy fallback：旧数据 key 是 computer_node_id
        legacy_key = str(getattr(downstream_seat, "computer_node_id", "") or "").strip()
        if legacy_key and legacy_key != ws_key:
            profile = profiles.get(legacy_key)
    if isinstance(profile, dict):
        ws_pol = str(profile.get("review_policy") or profile.get("reviewPolicy") or "").strip().lower()
        if ws_pol in {"force", "always", "on"}:
            return {"requires_review": True, "source": "workstation", "policy": "force"}
        if ws_pol in {"skip", "never", "off"}:
            return {"requires_review": False, "source": "workstation", "policy": "skip"}
    rp = cfg.get("review_policy") if isinstance(cfg.get("review_policy"), dict) else None
    project_default = ""
    if isinstance(rp, dict):
        project_default = str(rp.get("default") or rp.get("project_default") or "").strip().lower()
    project_default = project_default or "cross_workstation_only"
    if project_default == "always" or project_default == "force":
        return {"requires_review": True, "source": "project", "policy": project_default}
    if project_default == "never" or project_default == "skip":
        return {"requires_review": False, "source": "project", "policy": project_default}
    is_cross = _seats_cross_workstation(upstream_seat, downstream_seat)
    return {
        "requires_review": is_cross,
        "source": "project_default_cross_only",
        "policy": project_default,
    }


def _seat_workstation_key(seat: ProjectThreadWorkstation | None) -> str:
    """返回 NPC 所在的逻辑工位 key（优先 workstation_id，无则 fallback computer_node_id）。
    仅用于"同/跨工位"判定，不要用来表示电脑节点。"""
    if seat is None:
        return ""
    ws_id = str(getattr(seat, "workstation_id", "") or "").strip()
    if ws_id:
        return ws_id
    return str(getattr(seat, "computer_node_id", "") or "").strip()


def _seats_cross_workstation(
    upstream: ProjectThreadWorkstation | None,
    downstream: ProjectThreadWorkstation | None,
) -> bool:
    if upstream is None or downstream is None:
        return False
    return _seat_workstation_key(upstream) != _seat_workstation_key(downstream)


_DONE_STATES = frozenset({"done", "answered", "completed", "accepted", "closed"})
HIGH_RISK_NEED_MARKERS = (
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
    "写参数",
    "下发",
    "运动",
    "部署",
    "ros",
    "vla",
    "moveit",
    "firmware",
    "flash",
    "power on",
    "motion",
    "deploy",
    "hardware",
    "robot",
)


def _is_done_status(value: object) -> bool:
    return str(value or "").strip().lower() in _DONE_STATES


def _metadata_dict(value: object | None) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _seat_identity_values(seat: ProjectThreadWorkstation | None) -> set[str]:
    if seat is None:
        return set()
    values = {
        str(seat.id or ""),
        str(seat.config_id or ""),
        str(seat.name or ""),
        str(seat.agent_id or ""),
    }
    return {item.strip() for item in values if item and item.strip()}


def _seat_display_name(seat: ProjectThreadWorkstation | None) -> str:
    if seat is None:
        return ""
    return str(seat.name or seat.config_id or seat.id or "").strip()


def _seat_responsibility_text(seat: ProjectThreadWorkstation | None) -> str:
    if seat is None:
        return ""
    extra = _metadata_dict(getattr(seat, "extra_data", None))
    chunks = [
        getattr(seat, "description", None),
        getattr(seat, "notes", None),
        extra.get("responsibility"),
        extra.get("responsibility_text"),
        extra.get("role"),
        extra.get("accepted_task_types"),
        extra.get("skill_loadout"),
        extra.get("knowledge_paths"),
    ]
    return " ".join(str(chunk or "") for chunk in chunks).strip().lower()


def _need_text_for_risk(payload_or_requirement: object) -> str:
    if isinstance(payload_or_requirement, StructuredNeedCreate):
        parts = [
            payload_or_requirement.title,
            payload_or_requirement.why_needed,
            payload_or_requirement.required_capability,
            payload_or_requirement.expected_output,
            payload_or_requirement.input_context,
        ]
    else:
        requirement = payload_or_requirement
        parts = [
            getattr(requirement, "title", ""),
            getattr(requirement, "context_summary", ""),
            getattr(requirement, "expected_output", ""),
        ]
    return "\n".join(str(part or "") for part in parts).lower()


def _needs_human_review_for_risk(risk_level: str | None, text: str) -> tuple[bool, str | None]:
    normalized = str(risk_level or "").strip().lower()
    if normalized in {"high", "critical"}:
        return True, f"风险级别为 {normalized}，需要人类确认"
    for marker in HIGH_RISK_NEED_MARKERS:
        if marker.lower() in text:
            return True, f"包含高风险动作关键词：{marker}"
    return False, None


def _seat_can_accept_capability(seat: ProjectThreadWorkstation, required_capability: str) -> bool:
    capability = str(required_capability or "").strip().lower()
    if not capability:
        return False
    haystack = _seat_responsibility_text(seat)
    if capability in haystack:
        return True
    for token in [part for part in capability.replace("/", " ").replace(",", " ").split() if len(part) >= 2]:
        if token in haystack:
            return True
    return False


def _list_project_seats(db: Session, project_id: str) -> list[ProjectThreadWorkstation]:
    return list(
        db.scalars(
            select(ProjectThreadWorkstation)
            .where(ProjectThreadWorkstation.project_id == project_id)
            .order_by(ProjectThreadWorkstation.sort_order.asc(), ProjectThreadWorkstation.created_at.asc())
        )
    )


def _choose_need_target(
    db: Session,
    *,
    project_id: str,
    requester: ProjectThreadWorkstation,
    required_capability: str,
    suggested_assignee: str | None,
) -> tuple[ProjectThreadWorkstation | None, list[dict[str, object]], str | None]:
    seats = [seat for seat in _list_project_seats(db, project_id) if seat.id != requester.id]
    suggested = _resolve_seat(db, project_id, suggested_assignee)
    alternatives: list[dict[str, object]] = []
    for seat in seats:
        matched = _seat_can_accept_capability(seat, required_capability)
        score = 0
        reasons: list[str] = []
        if suggested is not None and seat.id == suggested.id:
            score += 100
            reasons.append("用户/NPC 指定")
        if _seat_workstation_key(seat) == _seat_workstation_key(requester):
            score += 20
            reasons.append("同工位")
        if matched:
            score += 50
            reasons.append("能力匹配")
        if str(seat.status or "").strip().lower() in {"online", "idle", "ready", "active"}:
            score += 5
            reasons.append("状态可用")
        if score > 0:
            alternatives.append(
                {
                    "seat_id": seat.id,
                    "seat_ref": seat.config_id,
                    "name": _seat_display_name(seat),
                    "workstation_id": seat.workstation_id,
                    "score": score,
                    "reasons": reasons or ["候选"],
                }
            )
    alternatives.sort(key=lambda item: int(item.get("score") or 0), reverse=True)
    if suggested is not None:
        return suggested, alternatives, None
    if alternatives:
        target_id = str(alternatives[0].get("seat_id") or "")
        return _resolve_seat(db, project_id, target_id), alternatives, None
    return None, alternatives, "没有找到匹配该能力的 NPC，请先在员工表补职责/skill，或手动指定承接 NPC"


def preview_need_route(db: Session, requirement_id: str, target_seat_id: str | None = None) -> dict[str, object]:
    requirement = get_requirement_or_404(db, requirement_id)
    project_id = str(requirement.project_id or "").strip()
    if not project_id:
        raise AppError("PROJECT_NOT_FOUND", "Need 缺少项目上下文", status_code=404)
    requester = _resolve_seat(db, project_id, requirement.from_agent)
    if requester is None:
        raise AppError("REQUESTER_SEAT_NOT_FOUND", "Need 发起 NPC 不存在", status_code=404)
    required_capability = ""
    risk_level = ""
    for line in str(requirement.context_summary or "").splitlines():
        if line.startswith("需要能力："):
            required_capability = line.split("：", 1)[1].strip()
        elif line.startswith("风险级别："):
            risk_level = line.split("：", 1)[1].strip()
    target, alternatives, blocked_reason = _choose_need_target(
        db,
        project_id=project_id,
        requester=requester,
        required_capability=required_capability or requirement.title,
        suggested_assignee=target_seat_id or requirement.target_seat_id or requirement.to_agent,
    )
    risk_review, risk_reason = _needs_human_review_for_risk(risk_level, _need_text_for_risk(requirement))
    review = {"requires_review": False, "source": "none", "policy": "auto"}
    if target is not None:
        review = _resolve_review_for_dispatch(db, requester, target)
    requires_review = bool(review.get("requires_review")) or risk_review or target is None
    review_reason = risk_reason or (
        "没有可路由目标" if target is None else "跨工位或策略要求审核" if review.get("requires_review") else "同工位/可信策略允许自动路由"
    )
    return {
        "need_id": requirement.id,
        "requester_seat_id": requester.id,
        "requester_name": _seat_display_name(requester),
        "recommended_assignee_id": target.id if target is not None else None,
        "recommended_assignee_ref": target.config_id if target is not None else None,
        "recommended_assignee_name": _seat_display_name(target),
        "alternatives": alternatives,
        "requires_review": requires_review,
        "review_reason": review_reason,
        "route_risk": "high" if risk_review else "review" if requires_review else "low",
        "will_create_tasks": []
        if target is None
        else [
            {
                "title": requirement.title,
                "assignee_seat_id": target.id,
                "assignee_seat_ref": target.config_id,
                "source_need_id": requirement.id,
            }
        ],
        "blocked_reason": blocked_reason,
        "review_policy": review,
    }


def create_structured_need(db: Session, payload: StructuredNeedCreate) -> dict[str, object]:
    requester = _resolve_seat(db, payload.project_id, payload.requester_seat_id)
    if requester is None:
        raise AppError("REQUESTER_SEAT_NOT_FOUND", "Need 发起 NPC 不存在", status_code=404)
    target, _alternatives, _blocked = _choose_need_target(
        db,
        project_id=payload.project_id,
        requester=requester,
        required_capability=payload.required_capability,
        suggested_assignee=payload.suggested_assignee,
    )
    risk_review, _risk_reason = _needs_human_review_for_risk(payload.risk_level, _need_text_for_risk(payload))
    opening = "\n".join(
        [
            payload.why_needed,
            "",
            f"需要能力：{payload.required_capability}",
            f"风险级别：{payload.risk_level}",
            f"期望产出：{payload.expected_output}",
            f"输入上下文：{payload.input_context}",
            "验收标准：",
            *[f"- {item}" for item in payload.acceptance_criteria],
        ]
    ).strip()
    requirement = repo.create_requirement(
        db,
        RequirementCreate(
            project_id=payload.project_id,
            title=payload.title,
            requirement_type="npc_structured_need",
            module=payload.module,
            priority=payload.priority,
            status="needs_human_review" if risk_review else "ready_to_route",
            from_agent=requester.id,
            to_agent=target.id if target is not None else None,
            target_seat_id=target.id if target is not None else None,
            context_summary=opening,
            expected_output=payload.expected_output,
            opening_message=opening,
        ),
    )
    preview = preview_need_route(db, requirement.id)
    route_result = None
    if payload.auto_route and not preview.get("requires_review") and not preview.get("blocked_reason"):
        route_result = route_need_to_task(
            db,
            requirement.id,
            NeedRouteRequest(
                target_seat_id=str(preview.get("recommended_assignee_id") or ""),
                approved=True,
                auto_dispatch=True,
                actor_type="agent",
                actor_id=requester.id,
                note="structured Need auto route",
            ),
        )
    return {"requirement": requirement, "route_preview": preview, "route_result": route_result}


def route_need_to_task(db: Session, requirement_id: str, payload: NeedRouteRequest) -> dict[str, object]:
    requirement = get_requirement_or_404(db, requirement_id)
    project_id = str(requirement.project_id or "").strip()
    if not project_id:
        raise AppError("PROJECT_NOT_FOUND", "Need 缺少项目上下文", status_code=404)
    preview = preview_need_route(db, requirement_id, target_seat_id=payload.target_seat_id)
    if preview.get("blocked_reason"):
        raise AppError("NEED_ROUTE_BLOCKED", str(preview["blocked_reason"]), status_code=409, details=preview)
    if preview.get("requires_review") and not payload.approved:
        requirement.status = "needs_human_review"
        db.add(requirement)
        db.commit()
        db.refresh(requirement)
        return {"requirement": requirement, "route_preview": preview, "task": None, "dispatch": None}
    target = _resolve_seat(db, project_id, str(preview.get("recommended_assignee_id") or ""))
    if target is None:
        raise AppError("TARGET_SEAT_NOT_FOUND", "承接 NPC 不存在", status_code=404, details=preview)

    acceptance = [
        "说明如何满足来源 Need",
        f"回执必须引用 Need：{requirement.id}",
    ]
    if requirement.expected_output:
        acceptance.append(requirement.expected_output)
    task = Task(
        project_id=project_id,
        title=requirement.title,
        description="\n".join(
            [
                f"来源 Need：{requirement.id}",
                f"提需求 NPC：{preview.get('requester_name') or requirement.from_agent}",
                f"承接 NPC：{_seat_display_name(target)}",
                "",
                requirement.context_summary or "",
            ]
        ).strip(),
        module=requirement.module,
        priority=requirement.priority if str(requirement.priority or "").startswith("P") else "P2",
        status="ready",
        assignee_agent_id=target.agent_id,
        acceptance_criteria=acceptance,
    )
    db.add(task)
    db.flush()
    from app.modules.tasks import repo as task_repo
    from app.modules.tasks.service import dispatch_task
    from app.modules.tasks.schemas import TaskDispatchCreate

    task_repo.create_task_event(
        db,
        task.id,
        "created_from_need",
        "由结构化 Need 路由生成任务",
        {
            "source_need_id": requirement.id,
            "requester_seat_id": requirement.from_agent,
            "assignee_seat_id": target.id,
            "assignee_seat_ref": target.config_id,
            "route_preview": preview,
        },
        actor_type=payload.actor_type,
        actor_id=payload.actor_id,
        commit=False,
    )
    requirement.task_id = task.id
    requirement.to_agent = target.id
    requirement.target_seat_id = target.id
    requirement.status = "routed"
    db.add(requirement)
    dispatch = None
    if payload.auto_dispatch:
        db.commit()
        db.refresh(task)
        dispatch = dispatch_task(
            db,
            task.id,
            TaskDispatchCreate(
                workstation_id=str(target.config_id or target.id),
                status="queued",
                notes=f"由 Need {requirement.id} 路由生成。",
            ),
            dispatched_by_user_id=payload.actor_id,
        )
        requirement = get_requirement_or_404(db, requirement_id)
    else:
        db.commit()
        db.refresh(task)
        db.refresh(requirement)
    return {"requirement": requirement, "route_preview": preview, "task": task, "dispatch": dispatch}


def create_requirement(db: Session, payload: RequirementCreate):
    return repo.create_requirement(db, payload)


def update_requirement(db: Session, requirement_id: str, payload: RequirementUpdate):
    requirement = get_requirement_or_404(db, requirement_id)
    return repo.update_requirement(db, requirement, payload)


def add_requirement_reply(db: Session, requirement_id: str, payload: RequirementReplyCreate):
    requirement = get_requirement_or_404(db, requirement_id)
    return repo.add_requirement_reply(db, requirement, payload)


def route_requirement(db: Session, requirement_id: str, payload: RequirementRouteRequest):
    requirement = get_requirement_or_404(db, requirement_id)
    before = {"to_agent": requirement.to_agent, "status": requirement.status}
    requirement.to_agent = payload.to_agent
    requirement.status = "routed"
    db.add(requirement)
    create_audit_log(
        db,
        project_id=requirement.project_id,
        task_id=requirement.task_id,
        actor_type="agent" if payload.from_agent else "system",
        actor_id=payload.from_agent,
        action="requirement.routed",
        resource_type="requirement",
        resource_id=requirement.id,
        before=before,
        after={"to_agent": requirement.to_agent, "status": requirement.status, "note": payload.note},
    )
    db.commit()
    db.refresh(requirement)
    return requirement


def dispatch_requirement(
    db: Session,
    requirement_id: str,
    payload: RequirementDispatchRequest,
    *,
    dedupe_key: str | None = None,
):
    requirement = get_requirement_or_404(db, requirement_id)
    before = {
        "to_agent": requirement.to_agent,
        "status": requirement.status,
    }
    target_ref = payload.target_id.strip()
    _validate_requirement_dispatch_target(db, requirement, target_type=payload.target_type, target_id=target_ref)
    if payload.target_type in {"agent", "workstation"}:
        requirement.to_agent = target_ref
    requirement.status = payload.status or "queued"
    db.add(requirement)
    try:
        dispatch_message = repo.create_requirement_collaboration_message(
            db,
            requirement,
            message_type="requirement_dispatch",
            title=payload.title or requirement.title,
            body=payload.body or payload.note or requirement.expected_output or requirement.context_summary or requirement.title,
            sender_type=payload.actor_type,
            sender_id=payload.actor_id,
            recipient_type=payload.target_type,
            recipient_id=target_ref,
            status=requirement.status,
            agent_id=target_ref if payload.target_type in {"agent", "workstation"} else None,
            dedupe_key=dedupe_key,
        )
    except IntegrityError:
        db.rollback()
        existing = _collaboration_message_by_dedupe_key(db, dedupe_key)
        if existing is None:
            raise
        requirement = get_requirement_or_404(db, requirement_id)
        return {"requirement": requirement, "message": existing}
    create_audit_log(
        db,
        project_id=requirement.project_id,
        task_id=requirement.task_id,
        actor_type=payload.actor_type,
        actor_id=payload.actor_id,
        action="requirement.dispatched",
        resource_type="requirement",
        resource_id=requirement.id,
        before=before,
        after={
            "to_agent": requirement.to_agent,
            "status": requirement.status,
            "target_type": payload.target_type,
            "target_id": target_ref,
            "message_id": dispatch_message.id,
        },
    )
    db.commit()
    db.refresh(requirement)
    db.refresh(dispatch_message)
    return {"requirement": requirement, "message": dispatch_message}


def _resolve_requirement_target_workstation(
    db: Session, requirement: Requirement
) -> ProjectThreadWorkstation | None:
    target = str(requirement.to_agent or "").strip()
    if not target:
        return None

    stmt = select(ProjectThreadWorkstation).where(ProjectThreadWorkstation.project_id == requirement.project_id)
    workstations = list(db.scalars(stmt))
    if not workstations:
        return None

    if target.startswith("ai:"):
        agent_id = target.split(":", 1)[1].strip()
        return next((item for item in workstations if (item.agent_id or "").strip() == agent_id), None)

    return next(
        (
            item
            for item in workstations
            if target in {item.id, item.config_id or "", item.name or "", item.agent_id or ""}
        ),
        None,
    )


def _requirement_messages(db: Session, requirement_id: str) -> list[CollaborationMessage]:
    stmt = (
        select(CollaborationMessage)
        .where(CollaborationMessage.requirement_id == requirement_id)
        .order_by(CollaborationMessage.created_at.asc(), CollaborationMessage.updated_at.asc())
    )
    return list(db.scalars(stmt))


def _requirement_has_final_reply(requirement_id: str, messages: list[CollaborationMessage], *, status: str | None = None) -> bool:
    for message in messages:
        if message.message_type != "requirement_final_reply":
            continue
        if status is None:
            return True
        if str(message.status or "").strip().lower() == status:
            return True
    return False


def _requirement_has_progress_ack(requirement_id: str, messages: list[CollaborationMessage]) -> bool:
    return any(_is_progress_ack_message(message) for message in messages)


def _requirement_matches_task_sync_target(
    db: Session,
    requirement: Requirement,
    *,
    workstation_id: str | None,
    agent_id: str | None,
) -> bool:
    target = str(requirement.to_agent or "").strip()
    cleaned_workstation_id = str(workstation_id or "").strip()
    cleaned_agent_id = str(agent_id or "").strip()
    if not target:
        return True

    candidates = {
        cleaned_workstation_id,
        cleaned_agent_id,
        f"ai:{cleaned_agent_id}" if cleaned_agent_id else "",
    }
    if target in candidates:
        return True

    workstation = _resolve_requirement_target_workstation(db, requirement)
    if workstation is None:
        return False
    return cleaned_workstation_id == workstation.config_id or (
        cleaned_agent_id != "" and cleaned_agent_id == (workstation.agent_id or "").strip()
    )


def _requirement_task_sync_rank(requirement: Requirement, messages: list[CollaborationMessage]) -> tuple[object, ...]:
    def _sort_stamp(value: object | None) -> float:
        if value is None:
            return -1.0
        return float(value.timestamp())  # type: ignore[union-attr]

    latest_dispatch = next(
        (message for message in reversed(messages) if message.message_type == "requirement_dispatch"),
        None,
    )
    latest_in_progress_reply = next(
        (
            message
            for message in reversed(messages)
            if _is_progress_ack_message(message)
        ),
        None,
    )
    return (
        1 if latest_in_progress_reply is not None else 0,
        1 if latest_dispatch is not None else 0,
        TASK_SYNC_STATUS_PRIORITY.get(str(requirement.status or "").strip().lower(), 0),
        _sort_stamp(latest_in_progress_reply.updated_at if latest_in_progress_reply is not None else None),
        _sort_stamp(latest_in_progress_reply.created_at if latest_in_progress_reply is not None else None),
        _sort_stamp(latest_dispatch.updated_at if latest_dispatch is not None else None),
        _sort_stamp(latest_dispatch.created_at if latest_dispatch is not None else None),
        _sort_stamp(requirement.updated_at),
        _sort_stamp(requirement.created_at),
        requirement.id,
    )


def _select_requirements_for_task_sync(
    db: Session,
    requirements: list[Requirement],
    *,
    workstation_id: str | None,
    agent_id: str | None,
) -> list[Requirement]:
    if not requirements:
        return []

    matched_requirements = [
        item
        for item in requirements
        if _requirement_matches_task_sync_target(
            db,
            item,
            workstation_id=workstation_id,
            agent_id=agent_id,
        )
    ]
    candidates = matched_requirements or requirements
    if len(candidates) == 1:
        return candidates
    if not matched_requirements:
        return []

    ranked = sorted(
        candidates,
        key=lambda requirement: _requirement_task_sync_rank(
            requirement,
            _requirement_messages(db, requirement.id),
        ),
        reverse=True,
    )
    return ranked[:1]


def sync_task_execution_to_requirements(
    db: Session,
    *,
    task_id: str,
    project_id: str | None,
    workstation_id: str | None,
    agent_id: str | None,
    reply_status: str,
    message: str,
    title: str | None = None,
    actor_id: str | None = None,
) -> dict[str, object]:
    stmt = select(Requirement).where(Requirement.task_id == task_id).order_by(Requirement.updated_at.asc(), Requirement.created_at.asc())
    if project_id:
        stmt = stmt.where(Requirement.project_id == project_id)
    linked_requirements = list(db.scalars(stmt))
    open_requirements = [item for item in linked_requirements if item.status in OPEN_REQUIREMENT_STATUSES]
    maintenance_done_requirements = [
        item
        for item in linked_requirements
        if item.status == "done" and _normalize_maintenance_template_title(item.title) in MAINTENANCE_TEMPLATE_TITLES
    ]
    candidate_requirements = open_requirements
    if reply_status == "done":
        candidate_requirements = open_requirements + [
            item for item in maintenance_done_requirements if item.id not in {requirement.id for requirement in open_requirements}
        ]
    requirements = _select_requirements_for_task_sync(
        db,
        candidate_requirements,
        workstation_id=workstation_id,
        agent_id=agent_id,
    )

    affected: list[dict[str, str]] = []
    sender_id = str(workstation_id or agent_id or actor_id or "AI/NPC").strip()
    for requirement in requirements:
        messages = _requirement_messages(db, requirement.id)
        if reply_status == "done" and _requirement_has_final_reply(requirement.id, messages, status="done"):
            _append_follow_up_affected(
                affected,
                _maybe_queue_follow_up_requirement(
                    db,
                    requirement,
                    workstation_id=workstation_id,
                    agent_id=agent_id,
                    actor_id=actor_id or sender_id,
                ),
            )
            continue
        if reply_status == "in_progress" and (
            _requirement_has_progress_ack(requirement.id, messages)
            or _requirement_has_final_reply(requirement.id, messages)
        ):
            continue

        if reply_status == "done":
            result = add_requirement_final_reply(
                db,
                requirement.id,
                RequirementFinalReplyRequest(
                    sender_type="agent",
                    sender_id=sender_id,
                    recipient_type="project",
                    recipient_id=requirement.project_id,
                    message=message,
                    status=reply_status,
                    title=title or requirement.title,
                ),
                dedupe_key=_auto_final_reply_dedupe_key(requirement.id, reply_status),
            )
        else:
            result = add_requirement_progress_ack(
                db,
                requirement.id,
                RequirementFinalReplyRequest(
                    sender_type="agent",
                    sender_id=sender_id,
                    recipient_type="project",
                    recipient_id=requirement.project_id,
                    message=message,
                    status="in_progress",
                    title=title or requirement.title,
                ),
                dedupe_key=_auto_progress_ack_dedupe_key(requirement.id),
            )
        affected.append(
            {
                "requirement_id": requirement.id,
                "title": requirement.title,
                "action": "final_reply" if reply_status == "done" else "minimal_ack",
                "message_id": result["message"].id,
            }
        )
        if reply_status == "done":
            _append_follow_up_affected(
                affected,
                _maybe_queue_follow_up_requirement(
                    db,
                    requirement,
                    workstation_id=workstation_id,
                    agent_id=agent_id,
                    actor_id=actor_id or sender_id,
                ),
            )

    return {
        "task_id": task_id,
        "reply_status": reply_status,
        "affected": affected,
        "count": len(affected),
    }


def run_requirement_autonomy_sweep(
    db: Session,
    project_id: str,
    *,
    actor_type: str = "agent",
    actor_id: str = "codex-platform-lead",
):
    active_requirements = list(
        db.scalars(
            select(Requirement)
            .where(
                Requirement.project_id == project_id,
                Requirement.to_agent.is_not(None),
                Requirement.status.in_(["waiting_response", "queued", "routed", "in_progress"]),
            )
            .order_by(Requirement.updated_at.asc(), Requirement.created_at.asc())
        )
    )
    completed_maintenance_requirements = list(
        db.scalars(
            select(Requirement)
            .where(
                Requirement.project_id == project_id,
                Requirement.to_agent.is_not(None),
                Requirement.status == "done",
                Requirement.title.in_(list(MAINTENANCE_TEMPLATE_TITLE_MATCHES)),
            )
            .order_by(Requirement.updated_at.asc(), Requirement.created_at.asc())
        )
    )
    requirements = active_requirements + [
        item for item in completed_maintenance_requirements if item.id not in {requirement.id for requirement in active_requirements}
    ]

    def _message_status(message: CollaborationMessage) -> str:
        return str(message.status or "").strip().lower()

    def _looks_like_done_message(message: CollaborationMessage) -> bool:
        status = _message_status(message)
        if status in {"done", "closed", "completed", "complete", "resolved"}:
            return True
        text_blob = f"{message.title or ''} {message.body or ''}".strip().lower()
        if not text_blob:
            return False
        return any(token in text_blob for token in ("done", "complete", "completed", "finished", "已完成", "完成"))

    def _is_done_final_reply_message(message: CollaborationMessage) -> bool:
        return (
            str(message.message_type or "").strip().lower() == "requirement_final_reply"
            and _message_status(message) == "done"
        )

    def _is_workstation_progress_message(
        message: CollaborationMessage,
        workstation: ProjectThreadWorkstation,
    ) -> bool:
        workstation_public_id = _workstation_dispatch_target_id(workstation)
        workstation_agent_id = (workstation.agent_id or "").strip()
        sender_type = str(message.sender_type or "").strip().lower()
        sender_id = (message.sender_id or "").strip()
        message_agent_id = (message.agent_id or "").strip()
        recipient_id = (message.recipient_id or "").strip()
        workstation_targets = {workstation.id, workstation_public_id, workstation_agent_id}
        return (
            (sender_type in {"agent", "workstation", "thread"} and sender_id in workstation_targets)
            or sender_id in workstation_targets
            or (message_agent_id != "" and message_agent_id in workstation_targets)
            or (message.recipient_type == "workstation" and recipient_id in workstation_targets)
        )

    def _collect_message_state(
        requirement_id: str,
        workstation: ProjectThreadWorkstation,
    ) -> dict[str, object]:
        messages = _requirement_messages(db, requirement_id)
        dispatch_messages = [item for item in messages if item.message_type == "requirement_dispatch"]
        final_messages = [item for item in messages if item.message_type == "requirement_final_reply"]
        done_final_messages = [item for item in final_messages if _message_status(item) == "done"]
        agent_progress = [
            item
            for item in messages
            if item.message_type in {"agent_report", "requirement_dispatch", "requirement_final_reply", "requirement_progress_ack"}
            and _is_workstation_progress_message(item, workstation)
        ]
        supplemental_progress = [
            item
            for item in messages
            if item.message_type in {"agent_report", "requirement_dispatch", "requirement_final_reply", "requirement_progress_ack"}
            and str(item.sender_type or "").strip().lower() in {"agent", "workstation", "runner"}
        ]
        latest_progress = agent_progress[-1] if agent_progress else None
        latest_done = next(
            (
                item
                for item in reversed(agent_progress)
                if _looks_like_done_message(item) or _is_done_final_reply_message(item)
            ),
            None,
        )
        if latest_done is None:
            latest_done = next(
                (
                    item
                    for item in reversed(supplemental_progress)
                    if _looks_like_done_message(item) or _is_done_final_reply_message(item)
                ),
                None,
            )
        latest_minimal_progress = next(
            (
                item
                for item in reversed(agent_progress)
                if item.message_type != "requirement_dispatch"
                and _message_status(item) in {"open", "active", "in_progress", "queued", "routed", "waiting_response", "answered"}
            ),
            None,
        )
        if latest_minimal_progress is None:
            latest_minimal_progress = next(
                (
                    item
                    for item in reversed(supplemental_progress)
                    if item.message_type != "requirement_dispatch"
                    and _message_status(item)
                    in {"open", "active", "in_progress", "queued", "routed", "waiting_response", "answered"}
                ),
                None,
            )
        if (
            latest_minimal_progress is None
            and latest_progress is not None
            and latest_progress.message_type != "requirement_dispatch"
            and not _looks_like_done_message(latest_progress)
        ):
            latest_minimal_progress = latest_progress
        return {
            "messages": messages,
            "dispatch_messages": dispatch_messages,
            "final_messages": final_messages,
            "done_final_messages": done_final_messages,
            "latest_progress": latest_progress,
            "latest_done": latest_done,
            "latest_minimal_progress": latest_minimal_progress,
        }

    dispatched = 0
    minimal_acks = 0
    finalized = 0
    followups = 0
    skipped = 0
    affected: list[dict[str, str]] = []

    for requirement in requirements:
        workstation = _resolve_requirement_target_workstation(db, requirement)
        if workstation is None:
            skipped += 1
            continue
        workstation_target_id = _workstation_dispatch_target_id(workstation)

        state = _collect_message_state(requirement.id, workstation)
        messages = state["messages"]
        dispatch_messages = state["dispatch_messages"]
        final_messages = state["final_messages"]
        done_final_messages = state["done_final_messages"]
        latest_progress = state["latest_progress"]
        latest_done = state["latest_done"]
        latest_minimal_progress = state["latest_minimal_progress"]

        action_taken = False

        if requirement.status != "done" and not dispatch_messages:
            dispatch_status = "in_progress" if latest_progress and _message_status(latest_progress) == "in_progress" else "queued"
            dispatch_body = (
                latest_progress.body
                if latest_progress and _message_status(latest_progress) == "in_progress"
                else requirement.expected_output or requirement.context_summary or requirement.title
            )
            dispatch_requirement(
                db,
                requirement.id,
                RequirementDispatchRequest(
                    actor_type=actor_type,
                    actor_id=actor_id,
                    target_type="workstation",
                    target_id=workstation_target_id,
                    note="autonomy sweep dispatch",
                    status=dispatch_status,
                    title=requirement.title,
                    body=dispatch_body,
                ),
            )
            dispatched += 1
            action_taken = True
            affected.append({"requirement_id": requirement.id, "title": requirement.title, "action": "dispatch"})

            state = _collect_message_state(requirement.id, workstation)
            messages = state["messages"]
            dispatch_messages = state["dispatch_messages"]
            final_messages = state["final_messages"]
            done_final_messages = state["done_final_messages"]
            latest_done = state["latest_done"]
            latest_minimal_progress = state["latest_minimal_progress"]

        if (
            requirement.status != "done"
            and not done_final_messages
            and latest_done is not None
            and latest_done.message_type != "requirement_final_reply"
        ):
            add_requirement_final_reply(
                db,
                requirement.id,
                RequirementFinalReplyRequest(
                    sender_type="agent",
                    sender_id=workstation.id,
                    recipient_type="project",
                    recipient_id=project_id,
                    message=latest_done.body or "已完成，已同步最终回执。",
                    status="done",
                    title=latest_done.title or requirement.title,
                ),
                dedupe_key=_auto_final_reply_dedupe_key(requirement.id, "done"),
            )
            finalized += 1
            action_taken = True
            affected.append({"requirement_id": requirement.id, "title": requirement.title, "action": "final_reply"})
        elif (
            requirement.status != "done"
            and not done_final_messages
            and not _requirement_has_progress_ack(requirement.id, messages)
            and latest_minimal_progress is not None
            and latest_minimal_progress.message_type not in {"requirement_final_reply", "requirement_progress_ack"}
        ):
            add_requirement_progress_ack(
                db,
                requirement.id,
                RequirementFinalReplyRequest(
                    sender_type="agent",
                    sender_id=workstation.id,
                    recipient_type="project",
                    recipient_id=project_id,
                    message=latest_minimal_progress.body or "已收到进展，继续处理中。",
                    status="in_progress",
                    title=latest_minimal_progress.title or requirement.title,
                ),
                dedupe_key=_auto_progress_ack_dedupe_key(requirement.id),
            )
            minimal_acks += 1
            action_taken = True
            affected.append({"requirement_id": requirement.id, "title": requirement.title, "action": "minimal_ack"})

        if not action_taken and (dispatch_messages or final_messages or requirement.status == "done"):
            skipped += 1

        refreshed_messages = _requirement_messages(db, requirement.id)
        refreshed_done = next((item for item in reversed(refreshed_messages) if _message_status(item) == "done"), None)
        if refreshed_done is not None:
            follow_up_result = _maybe_queue_follow_up_requirement(
                db,
                requirement,
                workstation_id=workstation_target_id,
                agent_id=(workstation.agent_id or "").strip() or None,
                actor_id=actor_id,
            )
            if follow_up_result is not None:
                if bool(follow_up_result.get("created")):
                    followups += 1
                _append_follow_up_affected(affected, follow_up_result)

    summary_title = "平台自治推进摘要"
    summary_body = (
        f"本轮自治推进完成：派单 {dispatched} 条，最小回执 {minimal_acks} 条，补最终回复 {finalized} 条，"
        f"续推后续复查 {followups} 条，跳过 {skipped} 条。"
    )
    create_collaboration_message(
        db,
        CollaborationMessageCreate(
            project_id=project_id,
            message_type="agent_report",
            title=summary_title,
            body=summary_body,
            sender_type=actor_type,
            sender_id=actor_id,
            recipient_type="project",
            recipient_id=project_id,
            status="done",
            agent_id=actor_id if actor_type == "agent" else None,
        ),
    )

    return {
        "project_id": project_id,
        "requirements": len(requirements),
        "dispatched": dispatched,
        "minimal_acks": minimal_acks,
        "finalized": finalized,
        "followups": followups,
        "skipped": skipped,
        "affected": affected,
    }


def add_requirement_final_reply(
    db: Session,
    requirement_id: str,
    payload: RequirementFinalReplyRequest,
    *,
    dedupe_key: str | None = None,
):
    requirement = get_requirement_or_404(db, requirement_id)
    existing = _existing_final_reply_result(db, requirement_id, dedupe_key=dedupe_key, payload=payload)
    if existing is not None:
        return existing
    if payload.recipient_type in {"agent", "workstation"} and payload.recipient_id:
        _validate_requirement_dispatch_target(
            db,
            requirement,
            target_type=payload.recipient_type,
            target_id=payload.recipient_id,
        )
    reply = RequirementReplyCreate(
        sender_type=payload.sender_type,
        sender_id=payload.sender_id,
        message=payload.message,
        status=payload.status,
    )
    try:
        with db.begin_nested():
            requirement_reply = repo.add_requirement_reply(db, requirement, reply, commit=False)
            collaboration_reply = repo.create_requirement_collaboration_message(
                db,
                requirement,
                message_type="requirement_final_reply",
                title=payload.title or requirement.title,
                body=payload.message,
                sender_type=payload.sender_type,
                sender_id=payload.sender_id,
                recipient_type=payload.recipient_type,
                recipient_id=payload.recipient_id,
                status=payload.status,
                agent_id=payload.sender_id if payload.sender_type == "agent" else None,
                dedupe_key=dedupe_key,
            )
            create_audit_log(
                db,
                project_id=requirement.project_id,
                task_id=requirement.task_id,
                actor_type=payload.sender_type,
                actor_id=payload.sender_id,
                action="requirement.final_reply",
                resource_type="collaboration_message",
                resource_id=collaboration_reply.id,
                after={
                    "requirement_id": requirement.id,
                    "status": payload.status,
                    "recipient_type": payload.recipient_type,
                    "recipient_id": payload.recipient_id,
                },
            )
        db.commit()
    except IntegrityError:
        existing = _existing_final_reply_result(db, requirement_id, dedupe_key=dedupe_key, payload=payload)
        if existing is not None:
            return existing
        raise
    db.refresh(requirement_reply)
    db.refresh(collaboration_reply)
    return {"reply": requirement_reply, "message": collaboration_reply}


def add_requirement_progress_ack(
    db: Session,
    requirement_id: str,
    payload: RequirementFinalReplyRequest,
    *,
    dedupe_key: str | None = None,
):
    requirement = get_requirement_or_404(db, requirement_id)
    existing = _existing_progress_ack_result(db, requirement_id, dedupe_key=dedupe_key, payload=payload)
    if existing is not None:
        return existing
    if payload.recipient_type in {"agent", "workstation"} and payload.recipient_id:
        _validate_requirement_dispatch_target(
            db,
            requirement,
            target_type=payload.recipient_type,
            target_id=payload.recipient_id,
        )
    reply = RequirementReplyCreate(
        sender_type=payload.sender_type,
        sender_id=payload.sender_id,
        message=payload.message,
        status="in_progress",
    )
    try:
        with db.begin_nested():
            requirement_reply = repo.add_requirement_reply(db, requirement, reply, commit=False)
            collaboration_reply = repo.create_requirement_collaboration_message(
                db,
                requirement,
                message_type="requirement_progress_ack",
                title=payload.title or requirement.title,
                body=payload.message,
                sender_type=payload.sender_type,
                sender_id=payload.sender_id,
                recipient_type=payload.recipient_type,
                recipient_id=payload.recipient_id,
                status="in_progress",
                agent_id=payload.sender_id if payload.sender_type == "agent" else None,
                dedupe_key=dedupe_key,
            )
            create_audit_log(
                db,
                project_id=requirement.project_id,
                task_id=requirement.task_id,
                actor_type=payload.sender_type,
                actor_id=payload.sender_id,
                action="requirement.minimal_ack",
                resource_type="collaboration_message",
                resource_id=collaboration_reply.id,
                after={
                    "requirement_id": requirement.id,
                    "status": "in_progress",
                    "recipient_type": payload.recipient_type,
                    "recipient_id": payload.recipient_id,
                },
            )
        db.commit()
    except IntegrityError:
        existing = _existing_progress_ack_result(db, requirement_id, dedupe_key=dedupe_key, payload=payload)
        if existing is not None:
            return existing
        raise
    db.refresh(requirement_reply)
    db.refresh(collaboration_reply)
    return {"reply": requirement_reply, "message": collaboration_reply}


def run_requirement_action(db: Session, requirement_id: str, action: str, payload: RequirementActionRequest):
    requirement = get_requirement_or_404(db, requirement_id)
    status_map = {"accept": "accepted", "escalate": "escalated", "close": "closed", "archive": "archived"}
    audit_map = {
        "accept": "requirement.accepted",
        "escalate": "requirement.escalated",
        "close": "requirement.closed",
        "archive": "requirement.archived",
    }
    if action not in status_map:
        raise AppError("BAD_REQUEST", f"unsupported requirement action: {action}", status_code=400)
    if action == "archive" and str(requirement.status or "").strip().lower() not in {
        "done",
        "answered",
        "completed",
        "accepted",
        "closed",
        "rejected",
        "cancelled",
        "archived",
    }:
        raise AppError("REQUIREMENT_NOT_DONE", "只有已完成或已关闭的需求才能从当前队列归档", status_code=409)
    before = {"status": requirement.status}
    requirement.status = payload.status or status_map[action]
    db.add(requirement)
    create_audit_log(
        db,
        project_id=requirement.project_id,
        task_id=requirement.task_id,
        actor_type=payload.actor_type,
        actor_id=payload.actor_id,
        action=audit_map[action],
        resource_type="requirement",
        resource_id=requirement.id,
        before=before,
        after={"status": requirement.status, "note": payload.note},
    )
    db.commit()
    db.refresh(requirement)
    return requirement


def promote_requirement_to_knowledge(db: Session, requirement_id: str, payload: RequirementPromoteRequest):
    requirement = get_requirement_or_404(db, requirement_id)
    before = {
        "status": requirement.status,
        "title": requirement.title,
        "module": requirement.module,
        "requirement_type": requirement.requirement_type,
    }
    requirement.status = payload.status or "accepted"
    if payload.target_type in {"knowledge", "knowledge_note"}:
        requirement.requirement_type = "knowledge_note"
    db.add(requirement)
    create_audit_log(
        db,
        project_id=requirement.project_id,
        task_id=requirement.task_id,
        actor_type=payload.actor_type,
        actor_id=payload.actor_id,
        action="requirement.promoted_to_knowledge",
        resource_type="requirement",
        resource_id=requirement.id,
        before=before,
        after={
            "status": requirement.status,
            "requirement_type": requirement.requirement_type,
            "target_type": payload.target_type,
            "title": requirement.title,
            "module": requirement.module,
            "note": payload.note,
        },
    )
    db.commit()
    db.refresh(requirement)
    return {"requirement_id": requirement.id, "target_type": payload.target_type, "promoted": True}


def find_similar_requirements(
    db: Session,
    *,
    title: str | None = None,
    module: str | None = None,
    task_id: str | None = None,
    project_ids: list[str] | None = None,
    limit: int = 20,
):
    stmt = select(Requirement).order_by(Requirement.updated_at.desc())
    if project_ids:
        stmt = (
            stmt.outerjoin(Task, Requirement.task_id == Task.id)
            .where(
                or_(
                    Requirement.project_id.in_(project_ids),
                    and_(Requirement.project_id.is_(None), Task.project_id.in_(project_ids)),
                )
            )
        )
    if module:
        stmt = stmt.where(Requirement.module == module)
    if task_id:
        stmt = stmt.where(Requirement.task_id == task_id)
    if title:
        like_value = f"%{title.strip()}%"
        stmt = stmt.where(or_(Requirement.title.ilike(like_value), Requirement.context_summary.ilike(like_value)))
    return list(db.scalars(stmt.limit(max(1, min(limit, 100)))))
