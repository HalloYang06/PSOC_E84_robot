from __future__ import annotations

import unittest

from vla_system.services.grounding_service import GroundingService
from vla_system.utils.json_schema import SceneObject, SceneRegion, SceneRelation, TaskDraft, TaskType


class GroundingServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = GroundingService()

    def test_left_reference_prefers_left_object(self) -> None:
        draft = TaskDraft(
            task_type=TaskType.HANDOVER,
            object_hint="",
            target_hint="user",
            spatial_hint="left",
            raw_text="把左边那个递给我",
            pronoun_only=True,
        )
        objects = [
            SceneObject(object_id="cup_01", class_name="cup", position=[0.2, 0.0, 0.7]),
            SceneObject(object_id="cup_02", class_name="cup", position=[0.5, 0.0, 0.7]),
        ]
        regions = []
        relations = [SceneRelation(subject="cup_01", predicate="left_of", object="cup_02")]
        result = self.service.rank(draft, objects, regions, relations)
        self.assertEqual(result.best_object().candidate_id, "cup_01")

    def test_source_region_prefers_shelf_object(self) -> None:
        draft = TaskDraft(
            task_type=TaskType.RETRIEVE_OBJECT,
            object_hint="thing",
            source_hint="shelf",
            spatial_hint="high",
            raw_text="把高架上的东西拿下来",
        )
        objects = [
            SceneObject(object_id="medicine_box_01", class_name="medicine_box", position=[0.2, 0.4, 1.2]),
            SceneObject(object_id="cup_01", class_name="cup", position=[0.4, 0.1, 0.7]),
        ]
        regions = [
            SceneRegion(region_id="shelf_01", region_type="shelf", position=[0.2, 0.6, 1.2]),
            SceneRegion(region_id="table_01", region_type="table", position=[0.4, 0.1, 0.7]),
        ]
        relations = [
            SceneRelation(subject="medicine_box_01", predicate="on", object="shelf_01"),
            SceneRelation(subject="cup_01", predicate="on", object="table_01"),
        ]
        result = self.service.rank(draft, objects, regions, relations)
        self.assertEqual(result.best_object().candidate_id, "medicine_box_01")


if __name__ == "__main__":
    unittest.main()
