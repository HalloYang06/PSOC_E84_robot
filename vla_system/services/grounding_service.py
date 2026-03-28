from __future__ import annotations

from vla_system.utils.json_schema import GroundingResult, RankedCandidate, SceneObject, SceneRegion, SceneRelation, TaskDraft
from vla_system.utils.relation_encoder import direction_score, height_score, object_in_region_type
from vla_system.utils.scene_encoder import (
    detect_canonical_term,
    load_task_schema,
    normalize_object_label,
    normalize_region_label,
    object_matches_hint,
)


class GroundingService:
    def __init__(self) -> None:
        self.schema = load_task_schema()
        self.region_aliases = self.schema.get("region_aliases", {})

    def rank(
        self,
        task_draft: TaskDraft,
        objects: list[SceneObject],
        regions: list[SceneRegion],
        relations: list[SceneRelation],
    ) -> GroundingResult:
        ranked_objects = sorted(
            (
                RankedCandidate(
                    candidate_id=scene_object.object_id,
                    score=self._score_object(task_draft, scene_object, objects, regions, relations),
                    candidate_type="object",
                )
                for scene_object in objects
            ),
            key=lambda item: item.score,
            reverse=True,
        )

        ranked_regions = sorted(
            (
                RankedCandidate(
                    candidate_id=region.region_id,
                    score=self._score_region(task_draft, region),
                    candidate_type="region",
                )
                for region in regions
            ),
            key=lambda item: item.score,
            reverse=True,
        )

        if task_draft.target_hint == "user":
            ranked_regions = [RankedCandidate(candidate_id="user", score=0.99, candidate_type="region")]

        return GroundingResult(ranked_objects=ranked_objects, ranked_regions=ranked_regions)

    def _score_object(
        self,
        task_draft: TaskDraft,
        scene_object: SceneObject,
        objects: list[SceneObject],
        regions: list[SceneRegion],
        relations: list[SceneRelation],
    ) -> float:
        score = 0.10
        normalized_class = normalize_object_label(scene_object.class_name)

        if task_draft.object_hint:
            if object_matches_hint(scene_object.class_name, task_draft.object_hint):
                score += 0.55
            elif task_draft.object_hint == normalized_class:
                score += 0.55
            elif task_draft.object_hint == "thing":
                score += 0.20
        else:
            score += 0.20

        if task_draft.object_hint == 'water':
            if normalized_class == 'bottle':
                score += 0.15
            elif normalized_class == 'cup':
                score -= 0.10

        if task_draft.source_hint and object_in_region_type(
            scene_object.object_id,
            task_draft.source_hint,
            relations,
            regions,
        ):
            score += 0.25

        if task_draft.spatial_hint in {"left", "right"}:
            score += 0.25 * direction_score(
                scene_object.object_id,
                task_draft.spatial_hint,
                objects,
                relations,
            )

        if task_draft.spatial_hint in {"high", "low"}:
            score += 0.20 * height_score(
                scene_object.object_id,
                task_draft.spatial_hint,
                objects,
            )

        if len(objects) == 1:
            score += 0.10

        return round(min(score, 0.99), 3)

    def _score_region(self, task_draft: TaskDraft, region: SceneRegion) -> float:
        if not task_draft.target_hint:
            return 0.10

        normalized_region = normalize_region_label(region.region_type)
        if normalized_region == task_draft.target_hint:
            return 0.95

        if detect_canonical_term(region.region_type, self.region_aliases) == task_draft.target_hint:
            return 0.90

        return 0.10

