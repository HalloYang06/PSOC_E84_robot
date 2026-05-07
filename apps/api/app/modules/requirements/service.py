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
    RequirementActionRequest,
    RequirementCreate,
    RequirementDispatchRequest,
    RequirementFinalReplyRequest,
    RequirementPromoteRequest,
    RequirementReplyCreate,
    RequirementRouteRequest,
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
        exists = any(cleaned in {item.id, item.config_id, item.name} for item in workstations)
    else:
        exists = any(cleaned == (item.agent_id or "") for item in workstations)
    if not exists:
        raise AppError(
            "TARGET_NOT_FOUND",
            f"dispatch target {target_type}:{cleaned} is not bound to this project",
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
    """按 项目→工位→NPC 结构解析 seat：在项目内按 id/config_id/name 三种引用方式匹配。"""
    cleaned = str(seat_ref or "").strip()
    if not cleaned or not project_id:
        return None
    stmt = select(ProjectThreadWorkstation).where(ProjectThreadWorkstation.project_id == project_id)
    for seat in db.scalars(stmt):
        if cleaned in {seat.id, seat.config_id, seat.name}:
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
    from app.db.models.project import Project  # local import to avoid cycle
    proj = db.get(Project, project_id)
    if proj is None:
        return {}
    cfg = getattr(proj, "collaboration_config", None)
    return cfg if isinstance(cfg, dict) else {}


def _resolve_review_for_dispatch(
    db: Session,
    upstream_seat: ProjectThreadWorkstation | None,
    downstream_seat: ProjectThreadWorkstation,
) -> dict:
    """三级 review policy：NPC > 工位 > 项目 default。返回 {requires_review, source, policy}。"""
    seat_pol = _seat_review_policy(downstream_seat)
    if seat_pol in {"force", "skip"}:
        return {"requires_review": seat_pol == "force", "source": "npc", "policy": seat_pol}
    cfg = _project_collab_config(db, downstream_seat.project_id)
    profiles = cfg.get("workstation_profiles") if isinstance(cfg.get("workstation_profiles"), dict) else {}
    node_id = str(getattr(downstream_seat, "computer_node_id", "") or "").strip()
    profile = profiles.get(node_id) if isinstance(profiles, dict) else None
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
    is_cross = bool(
        upstream_seat
        and str(getattr(upstream_seat, "computer_node_id", "") or "").strip()
        != str(getattr(downstream_seat, "computer_node_id", "") or "").strip()
    )
    return {
        "requires_review": is_cross,
        "source": "project_default_cross_only",
        "policy": project_default,
    }


def _trigger_dependent_requirements(
    db: Session,
    source_requirement: Requirement,
    *,
    actor_id: str | None = None,
) -> list[dict[str, object]]:
    """source_requirement 进入 done 时，按 项目→工位→NPC 派下游：
    - 找所有 dependency_requirement_id=source.id + trigger_kind=on_requirement_done + 还在 waiting_response 的 requirement
    - 对每个下游：sender = source.target_seat_id (上游 NPC), recipient = downstream.target_seat_id 的 workstation
    - 应用三级 review_policy 决定派单时 status=queued 或 pending_review
    """
    project_id = source_requirement.project_id
    if not project_id:
        return []
    stmt = select(Requirement).where(
        Requirement.dependency_requirement_id == source_requirement.id,
        Requirement.trigger_kind == "on_requirement_done",
        Requirement.status.in_(["waiting_response", "queued", "blocked"]),
    )
    affected: list[dict[str, object]] = []
    upstream_seat = _resolve_seat(db, project_id, source_requirement.target_seat_id)
    upstream_seat_id = upstream_seat.id if upstream_seat else (source_requirement.target_seat_id or "")
    for downstream in db.scalars(stmt):
        target_seat_ref = (downstream.target_seat_id or "").strip()
        if not target_seat_ref:
            continue
        downstream_seat = _resolve_seat(db, project_id, target_seat_ref)
        if downstream_seat is None:
            continue
        review = _resolve_review_for_dispatch(db, upstream_seat, downstream_seat)
        is_cross = bool(
            upstream_seat
            and str(getattr(upstream_seat, "computer_node_id", "") or "").strip()
            != str(getattr(downstream_seat, "computer_node_id", "") or "").strip()
        )
        new_status = "pending_review" if review["requires_review"] else "queued"
        downstream.to_agent = _workstation_dispatch_target_id(downstream_seat)
        downstream.status = new_status if not review["requires_review"] else "blocked"
        db.add(downstream)
        body_lines = [
            f"上游需求 [{source_requirement.title}] 已完成，请继续推进 [{downstream.title}]。",
            "",
            f"期望产出：{(downstream.expected_output or downstream.context_summary or '').strip() or '（沿用上游）'}",
            "",
            f"路由：项目 {project_id} → 工位 {getattr(downstream_seat, 'computer_node_id', '') or '未绑定'} → NPC {downstream_seat.name}",
            f"上游 NPC: {upstream_seat.name if upstream_seat else upstream_seat_id or '(未知)'}",
            f"跨工位：{'是' if is_cross else '否'}；审核：{'要' if review['requires_review'] else '免'}（来源：{review['source']}）",
        ]
        try:
            dispatch_message = repo.create_requirement_collaboration_message(
                db,
                downstream,
                message_type="requirement_dispatch",
                title=f"[自主合作] {source_requirement.title} → {downstream.title}",
                body="\n".join(body_lines),
                sender_type="agent",
                sender_id=upstream_seat_id or None,
                recipient_type="thread_workstation",
                recipient_id=str(downstream_seat.id),
                status=new_status,
                agent_id=_workstation_dispatch_target_id(downstream_seat),
                dedupe_key=f"auto_collab_dispatch:{source_requirement.id}:{downstream.id}",
            )
        except IntegrityError:
            db.rollback()
            existing = _collaboration_message_by_dedupe_key(
                db, f"auto_collab_dispatch:{source_requirement.id}:{downstream.id}"
            )
            if existing is None:
                continue
            dispatch_message = existing
        create_audit_log(
            db,
            project_id=project_id,
            task_id=downstream.task_id,
            actor_type="agent",
            actor_id=upstream_seat_id or None,
            action="requirement.autonomous_dispatched",
            resource_type="requirement",
            resource_id=downstream.id,
            before={"status": "waiting_response"},
            after={
                "status": new_status,
                "to_agent": downstream.to_agent,
                "source_requirement_id": source_requirement.id,
                "review": review,
                "is_cross_workstation": is_cross,
            },
        )
        affected.append({
            "requirement_id": downstream.id,
            "title": downstream.title,
            "source_seat_id": upstream_seat_id,
            "target_seat_id": _workstation_dispatch_target_id(downstream_seat),
            "is_cross_workstation": is_cross,
            "requires_review": review["requires_review"],
            "review_source": review["source"],
            "message_id": dispatch_message.id,
            "status": new_status,
        })
    if affected:
        db.commit()
    return affected


_DONE_STATES = frozenset({"done", "answered", "completed", "accepted", "closed"})


def _is_done_status(value: object) -> bool:
    return str(value or "").strip().lower() in _DONE_STATES


def create_requirement(db: Session, payload: RequirementCreate):
    return repo.create_requirement(db, payload)


def update_requirement(db: Session, requirement_id: str, payload: RequirementUpdate):
    requirement = get_requirement_or_404(db, requirement_id)
    before_done = _is_done_status(requirement.status)
    updated = repo.update_requirement(db, requirement, payload)
    after_done = _is_done_status(updated.status)
    if after_done and not before_done:
        _trigger_dependent_requirements(db, updated)
    return updated


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
    if _is_done_status(requirement.status):
        _trigger_dependent_requirements(db, requirement)
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
    status_map = {"accept": "accepted", "escalate": "escalated", "close": "closed"}
    audit_map = {
        "accept": "requirement.accepted",
        "escalate": "requirement.escalated",
        "close": "requirement.closed",
    }
    if action not in status_map:
        raise AppError("BAD_REQUEST", f"unsupported requirement action: {action}", status_code=400)
    before = {"status": requirement.status}
    before_done = _is_done_status(requirement.status)
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
    if _is_done_status(requirement.status) and not before_done:
        _trigger_dependent_requirements(db, requirement, actor_id=payload.actor_id)
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

