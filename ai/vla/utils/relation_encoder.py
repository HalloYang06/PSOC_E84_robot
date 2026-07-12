from __future__ import annotations

from ai.vla.utils.json_schema import SceneObject, SceneRegion, SceneRelation
from ai.vla.utils.scene_encoder import normalize_region_label


REGION_PREDICATES = {"on", "in", "inside"}


def object_region_ids(object_id: str, relations: list[SceneRelation]) -> list[str]:
    return [
        relation.object
        for relation in relations
        if relation.subject == object_id and relation.predicate in REGION_PREDICATES
    ]


def object_in_region_type(
    object_id: str,
    target_region_type: str,
    relations: list[SceneRelation],
    regions: list[SceneRegion],
) -> bool:
    region_by_id = {region.region_id: region for region in regions}
    for region_id in object_region_ids(object_id, relations):
        region = region_by_id.get(region_id)
        if region and normalize_region_label(region.region_type) == target_region_type:
            return True
    return False


def direction_score(
    object_id: str,
    direction: str,
    objects: list[SceneObject],
    relations: list[SceneRelation],
) -> float:
    positioned_objects = [item for item in objects if len(item.position) >= 1]
    if len(positioned_objects) >= 2:
        ordered = sorted(positioned_objects, key=lambda item: item.position[0])
        rank_map = {item.object_id: index for index, item in enumerate(ordered)}
        rank = rank_map.get(object_id)
        if rank is None:
            return 0.5
        if len(ordered) == 1:
            return 1.0
        normalized = rank / (len(ordered) - 1)
        return 1.0 - normalized if direction == "left" else normalized

    if direction not in {"left", "right"}:
        return 0.5

    relation_delta = 0
    for relation in relations:
        if relation.predicate != "left_of":
            continue
        if relation.subject == object_id:
            relation_delta += 1
        if relation.object == object_id:
            relation_delta -= 1

    if relation_delta == 0:
        return 0.5

    if direction == "left":
        return 1.0 if relation_delta > 0 else 0.0
    return 1.0 if relation_delta < 0 else 0.0


def height_score(object_id: str, direction: str, objects: list[SceneObject]) -> float:
    positioned_objects = [item for item in objects if len(item.position) >= 3]
    if len(positioned_objects) < 2:
        return 0.5

    ordered = sorted(positioned_objects, key=lambda item: item.position[2])
    rank_map = {item.object_id: index for index, item in enumerate(ordered)}
    rank = rank_map.get(object_id)
    if rank is None:
        return 0.5
    normalized = rank / (len(ordered) - 1)
    return normalized if direction == "high" else 1.0 - normalized
