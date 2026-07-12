from __future__ import annotations

from ai.vla.services.confirm_service import ConfirmationService
from ai.vla.services.grounding_service import GroundingService
from ai.vla.services.phase_service import PhaseService
from ai.vla.services.task_parser_service import TaskParserService
from ai.vla.utils.json_schema import CONFIG_DIR, ResolveTaskInput, ResolvedTask, load_json_yaml
from ai.vla.utils.scene_encoder import load_task_schema, normalize_object_label, scene_object_index
from ai.vla.utils.validators import validate_resolve_request, validate_resolved_task


class VLABridgeService:
    def __init__(self) -> None:
        self.task_parser = TaskParserService()
        self.grounding = GroundingService()
        self.phase = PhaseService()
        self.confirmation = ConfirmationService()
        self.schema = load_task_schema()
        self.thresholds = load_json_yaml(CONFIG_DIR / "thresholds.yaml")

    def resolve(self, payload: dict | ResolveTaskInput) -> ResolvedTask:
        request_payload = self._payload_to_dict(payload)
        validate_resolve_request(request_payload)
        request = payload if isinstance(payload, ResolveTaskInput) else ResolveTaskInput.from_dict(payload)

        task_draft = self.task_parser.parse(request.text)
        grounding = self.grounding.rank(task_draft, request.objects, request.regions, request.relations)
        confirmation = self.confirmation.judge(
            task_draft,
            grounding,
            request.objects,
            request.regions,
            request.relations,
        )

        best_object = grounding.best_object()
        best_region = grounding.best_region()

        object_id = ""
        if best_object and not confirmation.object_ambiguous:
            object_id = best_object.candidate_id

        target_region_id = ""
        if task_draft.target_hint == "user" and not confirmation.region_ambiguous:
            target_region_id = "user"
        elif best_region and not confirmation.region_ambiguous:
            target_region_id = best_region.candidate_id

        phase_prediction = self.phase.predict(
            task_type=task_draft.task_type,
            robot_state=request.robot_state,
            execution_history=request.execution_history,
            object_id=object_id,
            target_region_id=target_region_id,
        )

        grasp_type = self._choose_grasp_type(object_id, request.objects)
        speed = self._choose_speed(phase_prediction.phase.value, confirmation.need_confirmation)
        retry = any(event in self.thresholds.get("retry_events", []) for event in request.execution_history)

        confidence_parts = [phase_prediction.confidence, confirmation.confidence]
        if best_object is not None:
            confidence_parts.append(best_object.score)
        if best_region is not None and task_draft.target_hint and best_region.candidate_id != "user":
            confidence_parts.append(best_region.score)
        overall_confidence = round(min(confidence_parts), 3) if confidence_parts else 0.0

        resolved_task = ResolvedTask(
            task_type=task_draft.task_type.value,
            object_id=object_id,
            candidate_objects=[candidate.candidate_id for candidate in grounding.ranked_objects[:3]],
            target_region_id=target_region_id,
            phase=phase_prediction.phase.value,
            grasp_type=grasp_type,
            speed=speed,
            retry=retry,
            confidence=overall_confidence,
            need_confirmation=confirmation.need_confirmation,
            question=confirmation.question,
        )
        validate_resolved_task(resolved_task)
        return resolved_task

    def _choose_grasp_type(self, object_id: str, objects: list) -> str:
        if not object_id:
            return ""
        object_by_id = scene_object_index(objects)
        scene_object = object_by_id.get(object_id)
        if scene_object is None:
            return ""

        normalized_class = normalize_object_label(scene_object.class_name)
        grasp_map = self.schema.get("grasp_type_by_class", {})
        return grasp_map.get(normalized_class, grasp_map.get("default", "pinch_grasp"))

    def _choose_speed(self, phase: str, need_confirmation: bool) -> str:
        if need_confirmation or phase in set(self.thresholds.get("slow_phases", [])):
            return "slow"
        return "normal"

    def _payload_to_dict(self, payload: dict | ResolveTaskInput) -> dict:
        if isinstance(payload, dict):
            return payload
        return {
            "text": payload.text,
            "objects": [
                {
                    "object_id": item.object_id,
                    "class_name": item.class_name,
                    "bbox": item.bbox,
                    "position": item.position,
                }
                for item in payload.objects
            ],
            "regions": [
                {
                    "region_id": item.region_id,
                    "region_type": item.region_type,
                    "position": item.position,
                }
                for item in payload.regions
            ],
            "relations": [
                {
                    "subject": item.subject,
                    "predicate": item.predicate,
                    "object": item.object,
                }
                for item in payload.relations
            ],
            "robot_state": {
                "joint_state": payload.robot_state.joint_state,
                "ee_pose": payload.robot_state.ee_pose,
                "gripper_open": payload.robot_state.gripper_open,
                "has_object": payload.robot_state.has_object,
                "current_phase": payload.robot_state.current_phase,
            },
            "execution_history": payload.execution_history,
        }
