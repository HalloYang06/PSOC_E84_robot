from __future__ import annotations

import re
import secrets
from copy import deepcopy
from typing import Any


def _as_dict(raw: object | None) -> dict[str, Any]:
    if raw is None:
        return {}
    if hasattr(raw, "model_dump"):
        return deepcopy(raw.model_dump(mode="json"))  # type: ignore[call-arg]
    if isinstance(raw, dict):
        return deepcopy(raw)
    return deepcopy(dict(raw))


def _slugify_identifier(value: object | None, *, prefix: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    if not text:
        text = f"{prefix}-{secrets.token_hex(3)}"
    return text


def _resolve_reference(value: object | None, by_id: dict[str, str], by_label: dict[str, str]) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    candidate = str(value).strip()
    if not candidate:
        return None, None
    if candidate in by_id:
        return candidate, by_id[candidate]
    if candidate in by_label:
        resolved_id = by_label[candidate]
        return resolved_id, by_id[resolved_id]
    return candidate, candidate


def _normalize_path_list(value: object | None) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        items = [item.strip() for item in re.split(r"[\n,]+", value) if item.strip()]
        return items or None
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value if str(item).strip()]
        return items or None
    return [str(value).strip()] if str(value).strip() else None


def _normalize_workstation_role(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_collaboration_config(raw: object | None) -> dict[str, object]:
    data = _as_dict(raw)
    if not data:
        return {"thread_workstations": [], "ai_providers": [], "computer_nodes": []}

    provider_items = data.get("ai_providers") or data.get("providers") or []
    node_items = data.get("computer_nodes") or data.get("nodes") or []
    workstation_items = data.get("thread_workstations") or data.get("workstations") or []

    providers: list[dict[str, Any]] = []
    provider_labels: dict[str, str] = {}
    provider_ids_by_label: dict[str, str] = {}
    for index, item in enumerate(provider_items):
        provider = deepcopy(dict(item))
        provider_id = _slugify_identifier(provider.get("id") or provider.get("label") or provider.get("name") or index + 1, prefix="provider")
        provider_label = str(provider.get("label") or provider.get("name") or provider_id).strip() or provider_id
        provider["id"] = provider_id
        provider["label"] = provider_label
        provider["kind"] = provider.get("kind") or provider.get("type")
        provider["enabled"] = bool(provider.get("enabled", True))
        provider["endpoint"] = provider.get("endpoint") or provider.get("url")
        provider["model"] = provider.get("model") or provider.get("default_model")
        provider["sort_order"] = int(provider.get("sort_order", index) or index)
        providers.append(provider)
        provider_labels[provider_id] = provider_label
        provider_ids_by_label.setdefault(provider_label, provider_id)

    nodes: list[dict[str, Any]] = []
    node_labels: dict[str, str] = {}
    node_ids_by_label: dict[str, str] = {}
    for index, item in enumerate(node_items):
        node = deepcopy(dict(item))
        node_id = _slugify_identifier(node.get("id") or node.get("label") or node.get("name") or index + 1, prefix="node")
        node_label = str(node.get("label") or node.get("name") or node_id).strip() or node_id
        node["id"] = node_id
        node["label"] = node_label
        node["status"] = node.get("status") or "offline"
        node["runner_id"] = node.get("runner_id")
        node["connection_kind"] = node.get("connection_kind") or node.get("connection_type") or node.get("kind")
        node["workspace_root"] = node.get("workspace_root") or node.get("workspace") or node.get("workspace_path")
        node["git_root"] = node.get("git_root") or node.get("repo_root") or node.get("repository_root")
        node["read_paths"] = _normalize_path_list(node.get("read_paths") or node.get("read_dirs") or node.get("readable_paths"))
        node["write_paths"] = _normalize_path_list(node.get("write_paths") or node.get("write_dirs") or node.get("writable_paths"))
        node["host"] = node.get("host")
        node["os"] = node.get("os") or node.get("platform")
        node["sort_order"] = int(node.get("sort_order", index) or index)
        nodes.append(node)
        node_labels[node_id] = node_label
        node_ids_by_label.setdefault(node_label, node_id)

    workstations: list[dict[str, Any]] = []
    for index, item in enumerate(workstation_items):
        workstation = deepcopy(dict(item))
        workstation_name = str(workstation.get("name") or workstation.get("id") or workstation.get("agent_id") or f"workstation-{index + 1}").strip()
        workstation["id"] = str(workstation.get("id") or workstation_name).strip()
        workstation["name"] = workstation_name or workstation["id"]
        workstation["agent_id"] = workstation.get("agent_id")
        workstation["status"] = workstation.get("status") or "idle"
        workstation["responsibility"] = _normalize_workstation_role(
            workstation.get("responsibility") or workstation.get("responsibility_text") or workstation.get("role")
        )
        workstation["model"] = workstation.get("model") or workstation.get("default_model") or workstation.get("model_name")
        workstation["permission_level"] = _normalize_workstation_role(
            workstation.get("permission_level") or workstation.get("permissionLevel") or workstation.get("permission") or workstation.get("access_level")
        )
        workstation["read_paths"] = _normalize_path_list(
            workstation.get("read_paths") or workstation.get("read_dirs") or workstation.get("readable_paths")
        )
        workstation["write_paths"] = _normalize_path_list(
            workstation.get("write_paths") or workstation.get("write_dirs") or workstation.get("writable_paths")
        )
        workstation["description"] = workstation.get("description")
        workstation["notes"] = workstation.get("notes")
        workstation["sort_order"] = int(workstation.get("sort_order", index) or index)
        node_ref = workstation.get("computer_node_id") or workstation.get("computer_node")
        node_id, node_label = _resolve_reference(node_ref, node_labels, node_ids_by_label)
        if node_id is not None:
            workstation["computer_node_id"] = node_id
            workstation["computer_node"] = node_label
        provider_ref = workstation.get("ai_provider_id") or workstation.get("ai_provider")
        provider_id, provider_label = _resolve_reference(provider_ref, provider_labels, provider_ids_by_label)
        if provider_id is not None:
            workstation["ai_provider_id"] = provider_id
            workstation["ai_provider"] = provider_label
        workstations.append(workstation)

    extras = {
        key: value
        for key, value in data.items()
        if key not in {"thread_workstations", "workstations", "ai_providers", "providers", "computer_nodes", "nodes"}
    }

    return {
        **extras,
        "thread_workstations": workstations,
        "ai_providers": providers,
        "computer_nodes": nodes,
    }
