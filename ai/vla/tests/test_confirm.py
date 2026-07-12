from __future__ import annotations

import unittest

from ai.vla.services.confirm_service import ConfirmationService
from ai.vla.utils.json_schema import GroundingResult, RankedCandidate, SceneObject, SceneRegion, SceneRelation, TaskDraft, TaskType


class ConfirmationServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ConfirmationService()

    def test_confirmation_required_for_pronoun_with_close_scores(self) -> None:
        draft = TaskDraft(
            task_type=TaskType.HANDOVER,
            object_hint="",
            target_hint="user",
            spatial_hint="left",
            raw_text="把左边那个递给我",
            pronoun_only=True,
        )
        grounding = GroundingResult(
            ranked_objects=[
                RankedCandidate(candidate_id="cup_01", score=0.67, candidate_type="object"),
                RankedCandidate(candidate_id="cup_02", score=0.60, candidate_type="object"),
            ],
            ranked_regions=[
                RankedCandidate(candidate_id="user", score=0.99, candidate_type="region"),
            ],
        )
        objects = [
            SceneObject(object_id="cup_01", class_name="cup", position=[0.2, 0.0, 0.7]),
            SceneObject(object_id="cup_02", class_name="cup", position=[0.4, 0.0, 0.7]),
        ]
        result = self.service.judge(draft, grounding, objects, [], [SceneRelation(subject="cup_01", predicate="left_of", object="cup_02")])
        self.assertTrue(result.need_confirmation)
        self.assertTrue(result.object_ambiguous)
        self.assertIn("还是", result.question)

    def test_no_confirmation_for_clear_pick_and_place(self) -> None:
        draft = TaskDraft(
            task_type=TaskType.PICK_AND_PLACE,
            object_hint="water",
            target_hint="bed",
            raw_text="把水放到床上",
        )
        grounding = GroundingResult(
            ranked_objects=[
                RankedCandidate(candidate_id="bottle_01", score=0.90, candidate_type="object"),
                RankedCandidate(candidate_id="bottle_02", score=0.50, candidate_type="object"),
            ],
            ranked_regions=[
                RankedCandidate(candidate_id="bed_surface_01", score=0.95, candidate_type="region"),
            ],
        )
        objects = [
            SceneObject(object_id="bottle_01", class_name="bottle"),
            SceneObject(object_id="bottle_02", class_name="bottle"),
        ]
        regions = [SceneRegion(region_id="bed_surface_01", region_type="bed_surface")]
        result = self.service.judge(draft, grounding, objects, regions, [])
        self.assertFalse(result.need_confirmation)


if __name__ == "__main__":
    unittest.main()
