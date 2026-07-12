from __future__ import annotations

from typing import Any

from ai.vla.utils.json_schema import ResolvedTask
from ai.vla.utils.scene_encoder import load_task_schema


class SchemaValidationError(ValueError):
    pass


def validate_resolve_request(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise SchemaValidationError("resolve request must be a JSON object")

    required_keys = ("text", "objects", "regions", "relations", "robot_state", "execution_history")
    for key in required_keys:
        if key not in payload:
            raise SchemaValidationError(f"resolve request missing required field: {key}")

    if not isinstance(payload.get("text"), str) or not payload["text"].strip():
        raise SchemaValidationError("resolve request requires non-empty 'text'")

    _ensure_list_of_dicts(payload, "objects")
    _ensure_list_of_dicts(payload, "regions")
    _ensure_list_of_dicts(payload, "relations")

    robot_state = payload.get("robot_state")
    if not isinstance(robot_state, dict):
        raise SchemaValidationError("'robot_state' must be an object")

    execution_history = payload.get("execution_history")
    if not isinstance(execution_history, list) or not all(isinstance(item, str) for item in execution_history):
        raise SchemaValidationError("'execution_history' must be a list of strings")


def validate_resolved_task_payload(payload: dict[str, Any]) -> None:
    schema = load_task_schema()
    task_types = set(schema.get("task_types", []))
    phases = set(schema.get("phases", []))
    grasp_types = set(schema.get("grasp_types", []))
    speed_profiles = set(schema.get("speed_profiles", []))

    _ensure_enum(payload, "task_type", task_types)
    _ensure_optional_string(payload, "object_id")
    _ensure_string_list(payload, "candidate_objects")
    _ensure_optional_string(payload, "target_region_id")
    _ensure_enum(payload, "phase", phases)

    grasp_type = payload.get("grasp_type", "")
    if grasp_type and grasp_type not in grasp_types:
        raise SchemaValidationError(f"invalid 'grasp_type': {grasp_type}")

    _ensure_enum(payload, "speed", speed_profiles)

    if not isinstance(payload.get("retry"), bool):
        raise SchemaValidationError("'retry' must be a boolean")
    if not isinstance(payload.get("need_confirmation"), bool):
        raise SchemaValidationError("'need_confirmation' must be a boolean")
    if not isinstance(payload.get("question"), str):
        raise SchemaValidationError("'question' must be a string")

    confidence = payload.get("confidence")
    if not isinstance(confidence, (int, float)) or confidence < 0.0 or confidence > 1.0:
        raise SchemaValidationError("'confidence' must be between 0.0 and 1.0")


def validate_resolved_task(task: ResolvedTask) -> None:
    validate_resolved_task_payload(task.to_dict())


def _ensure_list_of_dicts(payload: dict[str, Any], key: str) -> None:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise SchemaValidationError(f"'{key}' must be a list of objects")


def _ensure_string_list(payload: dict[str, Any], key: str) -> None:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SchemaValidationError(f"'{key}' must be a list of strings")


def _ensure_optional_string(payload: dict[str, Any], key: str) -> None:
    value = payload.get(key)
    if not isinstance(value, str):
        raise SchemaValidationError(f"'{key}' must be a string")


def _ensure_enum(payload: dict[str, Any], key: str, allowed: set[str]) -> None:
    value = payload.get(key)
    if not isinstance(value, str) or value not in allowed:
        raise SchemaValidationError(f"invalid '{key}': {value}")
