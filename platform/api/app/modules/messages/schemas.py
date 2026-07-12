from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


ALLOWED_MESSAGE_TYPES = {
    "task_message",
    "requirement_message",
    "approval_message",
    "handoff_message",
    "comment_message",
    "system_message",
}


class MessageCreate(BaseModel):
    project_id: str | None = None
    entity_type: str | None = Field(default=None, max_length=32)
    entity_id: str | None = Field(default=None, max_length=64)
    message_type: str = "comment_message"
    sender_type: str = "system"
    sender_id: str | None = None
    body: str = Field(min_length=1)
    parent_message_id: str | None = None
    data: dict = Field(default_factory=dict)


class MessageRead(BaseModel):
    id: str
    project_id: str | None
    entity_type: str
    entity_id: str
    message_type: str
    sender_type: str
    sender_id: str | None
    body: str
    parent_message_id: str | None
    data: dict
    created_at: datetime | None
    updated_at: datetime | None

    class Config:
        from_attributes = True


class MessageThreadRead(BaseModel):
    entity_type: str
    entity_id: str
    project_id: str | None
    messages: list[MessageRead]
