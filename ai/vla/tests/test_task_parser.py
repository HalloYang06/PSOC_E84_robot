from __future__ import annotations

import unittest

from ai.vla.services.task_parser_service import TaskParserService


class TaskParserServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = TaskParserService()

    def test_parse_pick_and_place(self) -> None:
        draft = self.service.parse("把水放到床上")
        self.assertEqual(draft.task_type.value, "pick_and_place")
        self.assertEqual(draft.object_hint, "water")
        self.assertEqual(draft.target_hint, "bed")

    def test_parse_handover_with_left_reference(self) -> None:
        draft = self.service.parse("把左边那个递给我")
        self.assertEqual(draft.task_type.value, "handover")
        self.assertEqual(draft.spatial_hint, "left")
        self.assertEqual(draft.target_hint, "user")
        self.assertTrue(draft.pronoun_only)


if __name__ == "__main__":
    unittest.main()
