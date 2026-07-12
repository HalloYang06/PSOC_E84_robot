from __future__ import annotations

from pydantic import BaseModel


class DevelopmentWorkshopModuleRead(BaseModel):
    id: str
    label: str
    station: str
    map_scene: str
    map_location: str
    detail: str
    modes: list[str]
    backend_anchor: str
    runner_capabilities: list[str]
    ai_responsibilities: list[str]
    npc_role_templates: list[str]
    assignment_keywords: list[str]
    next_actions: list[str]
    approval_policy: str
    risk_level: str


class DevelopmentWorkshopGuardrailRead(BaseModel):
    id: str
    label: str
    reason: str
    required_gate: str


class DevelopmentWorkshopFrameworkRead(BaseModel):
    project_id: str | None = None
    product_scope: list[str]
    runtime_scope: list[str]
    primary_loop: list[str]
    modules: list[DevelopmentWorkshopModuleRead]
    guardrails: list[DevelopmentWorkshopGuardrailRead]
