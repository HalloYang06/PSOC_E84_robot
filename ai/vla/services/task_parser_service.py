from __future__ import annotations

from ai.vla.utils.json_schema import TaskDraft, TaskType
from ai.vla.utils.scene_encoder import alias_map, detect_canonical_term, load_task_schema


class TaskParserService:
    def __init__(self) -> None:
        self.schema = load_task_schema()
        self.object_aliases = alias_map("object_aliases")
        self.region_aliases = alias_map("region_aliases")
        self.spatial_aliases = alias_map("spatial_aliases")
        self.task_keywords = self.schema.get("task_keywords", {})

    def parse(self, text: str) -> TaskDraft:
        normalized_text = text.strip()
        task_type = self._detect_task_type(normalized_text)
        object_hint = self._detect_object_hint(normalized_text)
        region_hint = detect_canonical_term(normalized_text, self.region_aliases)
        spatial_hint = detect_canonical_term(normalized_text, self.spatial_aliases)

        target_hint = ""
        source_hint = ""

        if task_type == TaskType.PICK_AND_PLACE:
            target_hint = region_hint
        else:
            if region_hint and region_hint != "user":
                source_hint = region_hint
            if task_type == TaskType.HANDOVER:
                target_hint = "user"

        pronoun_only = any(token in normalized_text for token in ["那个", "这个"]) and object_hint in {"", "thing"}

        return TaskDraft(
            task_type=task_type,
            object_hint=object_hint,
            target_hint=target_hint,
            source_hint=source_hint,
            spatial_hint=spatial_hint,
            raw_text=normalized_text,
            pronoun_only=pronoun_only,
        )

    def _detect_task_type(self, text: str) -> TaskType:
        if self._contains_any(text, self.task_keywords.get("pick_and_place", [])):
            return TaskType.PICK_AND_PLACE
        if self._contains_any(text, self.task_keywords.get("handover", [])):
            return TaskType.HANDOVER
        if self._contains_any(text, self.task_keywords.get("retrieve_object", [])):
            return TaskType.RETRIEVE_OBJECT
        return TaskType.RETRIEVE_OBJECT

    def _detect_object_hint(self, text: str) -> str:
        object_hint = detect_canonical_term(text, self.object_aliases)
        if object_hint:
            return object_hint
        if "东西" in text or "物品" in text:
            return "thing"
        return ""

    @staticmethod
    def _contains_any(text: str, keywords: list[str]) -> bool:
        return any(keyword in text for keyword in keywords)
