from __future__ import annotations

from vla_system.utils.json_schema import GroundingResult, SceneObject, SceneRegion, SceneRelation, TaskDraft
from vla_system.utils.relation_encoder import object_region_ids
from vla_system.utils.scene_encoder import (
    display_name,
    normalize_object_label,
    normalize_region_label,
    scene_object_index,
    scene_region_index,
)


def describe_object_candidate(
    object_id: str,
    objects: list[SceneObject],
    regions: list[SceneRegion],
    relations: list[SceneRelation],
) -> str:
    object_by_id = scene_object_index(objects)
    region_by_id = scene_region_index(regions)
    scene_object = object_by_id.get(object_id)
    if scene_object is None:
        return object_id

    object_name = display_name(normalize_object_label(scene_object.class_name))
    linked_region_ids = object_region_ids(object_id, relations)
    if linked_region_ids:
        region = region_by_id.get(linked_region_ids[0])
        if region:
            region_name = display_name(normalize_region_label(region.region_type))
            return f"{region_name}上的{object_name}({object_id})"

    return f"{object_name}({object_id})"


def describe_region_candidate(region_id: str, regions: list[SceneRegion]) -> str:
    region_by_id = scene_region_index(regions)
    region = region_by_id.get(region_id)
    if region is None:
        return region_id
    return f"{display_name(normalize_region_label(region.region_type))}({region_id})"


def build_confirmation_question(
    task_draft: TaskDraft,
    grounding: GroundingResult,
    objects: list[SceneObject],
    regions: list[SceneRegion],
    relations: list[SceneRelation],
    max_candidates: int,
    object_ambiguous: bool,
    region_ambiguous: bool,
) -> str:
    if object_ambiguous:
        labels = [
            describe_object_candidate(candidate.candidate_id, objects, regions, relations)
            for candidate in grounding.ranked_objects[:max_candidates]
        ]
        if len(labels) == 1:
            return f"我不确定是不是要拿{labels[0]}，请确认。"
        if len(labels) >= 2:
            return f"我不确定目标物体，是要拿{labels[0]}，还是{labels[1]}？"
        return "我没有找到明确的目标物体，请确认你想操作哪个物体。"

    if region_ambiguous:
        labels = [
            describe_region_candidate(candidate.candidate_id, regions)
            for candidate in grounding.ranked_regions[:max_candidates]
        ]
        if len(labels) >= 2:
            return f"目标区域不明确，是要放到{labels[0]}，还是{labels[1]}？"
        return "目标区域不明确，请确认你要放到哪里。"

    return ""