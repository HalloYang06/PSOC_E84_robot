from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ReceiptKind = Literal["ack", "progress", "done", "reject"]


class ReceiptCreate(BaseModel):
    """提交回执：sender_seat_id 为发送方 NPC（必填）。
    recipient_seat_id 留空时按 parent_requirement 解析为原派单发起人，跨工位也直返发起人。"""

    receipt_kind: ReceiptKind
    parent_requirement_id: str = Field(min_length=1, max_length=64)
    sender_seat_id: str = Field(min_length=1, max_length=64)
    recipient_seat_id: str | None = Field(default=None, max_length=64)
    title: str | None = Field(default=None, max_length=300)
    body: str = Field(min_length=1)
    artifacts: dict[str, Any] | None = None
    reject_reason: str | None = Field(default=None, max_length=400)
    suggested_seat_id: str | None = Field(default=None, max_length=64)
    blocked_reason_code: str | None = Field(default=None, max_length=80)
    blocked_reason_label: str | None = Field(default=None, max_length=200)
    retryable: bool | None = None
    log_available: bool | None = None
    split_suggested: bool | None = None
    evidence_complete: bool | None = None


class ReceiptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None = None
    receipt_kind: ReceiptKind
    parent_requirement_id: str
    sender_seat_id: str | None = None
    recipient_seat_id: str | None = None
    cross_workstation: bool = False
    title: str | None = None
    body: str
    extra_data: dict[str, Any] | None = None
    authoritative_seat_id: str | None = None
    authoritative_seat_ref: str | None = None
    authoritative_target_seat_id: str | None = None
    historical_alias_non_authoritative: bool = False
    created_at: str | None = None

    @classmethod
    def _authority_from_extra(cls, extra_data: dict[str, Any] | None) -> dict[str, Any]:
        extra = extra_data if isinstance(extra_data, dict) else {}
        return {
            "authoritative_seat_id": str(
                extra.get("authoritative_seat_id")
                or extra.get("authoritative_sender_seat_id")
                or ""
            ).strip()
            or None,
            "authoritative_seat_ref": str(extra.get("authoritative_seat_ref") or "").strip() or None,
            "authoritative_target_seat_id": str(extra.get("authoritative_target_seat_id") or "").strip() or None,
            "historical_alias_non_authoritative": bool(extra.get("historical_alias_non_authoritative")),
        }

    @classmethod
    def with_authority(cls, **data: Any) -> "ReceiptRead":
        merged = dict(data)
        merged.update(cls._authority_from_extra(merged.get("extra_data")))
        return cls(**merged)
