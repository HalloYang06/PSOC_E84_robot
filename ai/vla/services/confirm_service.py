from __future__ import annotations

from ai.vla.utils.json_schema import CONFIG_DIR, ConfirmationResult, GroundingResult, SceneObject, SceneRegion, SceneRelation, TaskDraft, load_json_yaml
from ai.vla.utils.prompt_builder import build_confirmation_question


class ConfirmationService:
    def __init__(self) -> None:
        self.thresholds = load_json_yaml(CONFIG_DIR / "thresholds.yaml")

    def judge(
        self,
        task_draft: TaskDraft,
        grounding: GroundingResult,
        objects: list[SceneObject],
        regions: list[SceneRegion],
        relations: list[SceneRelation],
    ) -> ConfirmationResult:
        top_object = grounding.best_object()
        top_region = grounding.best_region()

        object_gap = self._gap(grounding.ranked_objects)
        region_gap = self._gap(grounding.ranked_regions)

        object_ambiguous = False
        region_ambiguous = False

        if top_object is None:
            object_ambiguous = True
        else:
            if top_object.score < float(self.thresholds["min_object_score"]):
                object_ambiguous = True
            if len(grounding.ranked_objects) > 1 and object_gap < float(self.thresholds["ambiguity_gap"]):
                object_ambiguous = True
            if task_draft.pronoun_only and len(grounding.ranked_objects) > 1:
                required_margin = float(self.thresholds["pronoun_margin"])
                object_ambiguous = object_ambiguous or object_gap < required_margin

        if task_draft.target_hint:
            if top_region is None:
                region_ambiguous = True
            elif top_region.candidate_id != "user":
                if top_region.score < float(self.thresholds["min_region_score"]):
                    region_ambiguous = True
                if len(grounding.ranked_regions) > 1 and region_gap < float(self.thresholds["ambiguity_gap"]):
                    region_ambiguous = True

        need_confirmation = object_ambiguous or region_ambiguous
        question = build_confirmation_question(
            task_draft=task_draft,
            grounding=grounding,
            objects=objects,
            regions=regions,
            relations=relations,
            max_candidates=int(self.thresholds["max_confirmation_candidates"]),
            object_ambiguous=object_ambiguous,
            region_ambiguous=region_ambiguous,
        )
        confidence = min(
            top_object.score if top_object else 0.0,
            top_region.score if top_region and task_draft.target_hint else 1.0,
        )

        return ConfirmationResult(
            need_confirmation=need_confirmation,
            question=question,
            object_ambiguous=object_ambiguous,
            region_ambiguous=region_ambiguous,
            confidence=confidence,
        )

    @staticmethod
    def _gap(candidates: list) -> float:
        if len(candidates) < 2:
            return 1.0
        return round(candidates[0].score - candidates[1].score, 3)
