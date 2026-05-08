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
    created_at: str | None = None
