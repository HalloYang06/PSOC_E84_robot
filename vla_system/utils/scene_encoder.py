from __future__ import annotations

from functools import lru_cache
from typing import Any

from vla_system.utils.json_schema import CONFIG_DIR, SceneObject, SceneRegion, load_json_yaml


@lru_cache(maxsize=1)
def load_task_schema() -> dict[str, Any]:
    return load_json_yaml(CONFIG_DIR / "task_schema.yaml")


def alias_map(name: str) -> dict[str, list[str]]:
    return dict(load_task_schema().get(name, {}))


def display_name(canonical_label: str) -> str:
    schema = load_task_schema()
    return schema.get("display_names", {}).get(canonical_label, canonical_label)


def detect_canonical_term(text: str, aliases: dict[str, list[str]]) -> str:
    best_label = ""
    best_length = -1
    for canonical, variants in aliases.items():
        for token in [canonical, *variants]:
            if token and token in text and len(token) > best_length:
                best_label = canonical
                best_length = len(token)
    return best_label


def normalize_object_label(label: str) -> str:
    return detect_canonical_term(label.lower(), alias_map("object_aliases")) or label.lower()


def normalize_region_label(label: str) -> str:
    return detect_canonical_term(label.lower(), alias_map("region_aliases")) or label.lower()


def object_matches_hint(object_label: str, object_hint: str) -> bool:
    if not object_hint:
        return False
    schema = load_task_schema()
    normalized_object = normalize_object_label(object_label)
    compatibility = schema.get("object_compatibility", {})
    allowed = set(compatibility.get(object_hint, [object_hint]))
    return normalized_object in allowed or normalized_object == object_hint


def scene_object_index(objects: list[SceneObject]) -> dict[str, SceneObject]:
    return {item.object_id: item for item in objects}


def scene_region_index(regions: list[SceneRegion]) -> dict[str, SceneRegion]:
    return {item.region_id: item for item in regions}
