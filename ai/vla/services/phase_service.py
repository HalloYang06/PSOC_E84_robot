from __future__ import annotations

from ai.vla.utils.json_schema import Phase, PhasePrediction, RobotState, TaskType


class PhaseService:
    def predict(
        self,
        task_type: TaskType,
        robot_state: RobotState,
        execution_history: list[str],
        object_id: str,
        target_region_id: str,
    ) -> PhasePrediction:
        if robot_state.current_phase == Phase.STOP.value or "force_stop" in execution_history:
            return PhasePrediction(phase=Phase.STOP, confidence=0.98)

        if not object_id:
            return PhasePrediction(phase=Phase.SEARCH, confidence=0.72)

        if any(event == "grasp_succeeded" for event in execution_history[-2:]):
            return PhasePrediction(phase=Phase.LIFT, confidence=0.88)

        if robot_state.has_object:
            if task_type == TaskType.HANDOVER:
                return PhasePrediction(phase=Phase.HANDOVER, confidence=0.92)
            if target_region_id:
                return PhasePrediction(phase=Phase.PLACE, confidence=0.90)
            return PhasePrediction(phase=Phase.RETURN, confidence=0.75)

        if robot_state.current_phase == Phase.APPROACH.value:
            return PhasePrediction(phase=Phase.ALIGN, confidence=0.83)
        if robot_state.current_phase == Phase.ALIGN.value:
            return PhasePrediction(phase=Phase.GRASP, confidence=0.85)
        if robot_state.current_phase == Phase.GRASP.value and robot_state.has_object:
            return PhasePrediction(phase=Phase.LIFT, confidence=0.88)

        if not robot_state.gripper_open:
            return PhasePrediction(phase=Phase.GRASP, confidence=0.84)

        if any(event == "approach_complete" for event in execution_history[-2:]):
            return PhasePrediction(phase=Phase.ALIGN, confidence=0.81)

        return PhasePrediction(phase=Phase.APPROACH, confidence=0.80)
