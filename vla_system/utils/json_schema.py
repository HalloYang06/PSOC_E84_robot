from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PACKAGE_ROOT / "configs"


class TaskType(StrEnum):
    PICK_AND_PLACE = "pick_and_place"
    RETRIEVE_OBJECT = "retrieve_object"
    HANDOVER = "handover"


class Phase(StrEnum):
    SEARCH = "search"
    APPROACH = "approach"
    ALIGN = "align"
    GRASP = "grasp"
    LIFT = "lift"
    HANDOVER = "handover"
    PLACE = "place"
    RETURN = "return"
    STOP = "stop"


@dataclass(slots=True)
class SceneObject:
    object_id: str
    class_name: str
    bbox: list[int] = field(default_factory=list)
    position: list[float] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SceneObject":
        return cls(
            object_id=str(data.get("object_id", "")),
            class_name=str(data.get("class_name", "")),
            bbox=list(data.get("bbox", [])),
            position=list(data.get("position", [])),
        )


@dataclass(slots=True)
class SceneRegion:
    region_id: str
    region_type: str
    position: list[float] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SceneRegion":
        return cls(
            region_id=str(data.get("region_id", "")),
            region_type=str(data.get("region_type", "")),
            position=list(data.get("position", [])),
        )


@dataclass(slots=True)
class SceneRelation:
    subject: str
    predicate: str
    object: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SceneRelation":
        return cls(
            subject=str(data.get("subject", "")),
            predicate=str(data.get("predicate", "")),
            object=str(data.get("object", "")),
        )


@dataclass(slots=True)
class RobotState:
    joint_state: list[float] = field(default_factory=list)
    ee_pose: list[float] = field(default_factory=list)
    gripper_open: bool = True
    has_object: bool = False
    current_phase: str = Phase.SEARCH.value

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RobotState":
        data = data or {}
        return cls(
            joint_state=list(data.get("joint_state", [])),
            ee_pose=list(data.get("ee_pose", [])),
            gripper_open=bool(data.get("gripper_open", True)),
            has_object=bool(data.get("has_object", False)),
            current_phase=str(data.get("current_phase", Phase.SEARCH.value)),
        )


@dataclass(slots=True)
class ResolveTaskInput:
    text: str
    objects: list[SceneObject] = field(default_factory=list)
    regions: list[SceneRegion] = field(default_factory=list)
    relations: list[SceneRelation] = field(default_factory=list)
    robot_state: RobotState = field(default_factory=RobotState)
    execution_history: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResolveTaskInput":
        return cls(
            text=str(data.get("text", "")),
            objects=[SceneObject.from_dict(item) for item in data.get("objects", [])],
            regions=[SceneRegion.from_dict(item) for item in data.get("regions", [])],
            relations=[SceneRelation.from_dict(item) for item in data.get("relations", [])],
            robot_state=RobotState.from_dict(data.get("robot_state")),
            execution_history=[str(item) for item in data.get("execution_history", [])],
        )


@dataclass(slots=True)
class TaskDraft:
    task_type: TaskType
    object_hint: str = ""
    target_hint: str = ""
    source_hint: str = ""
    spatial_hint: str = ""
    raw_text: str = ""
    pronoun_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type.value,
            "object_hint": self.object_hint,
            "target_hint": self.target_hint,
            "source_hint": self.source_hint,
            "spatial_hint": self.spatial_hint,
            "raw_text": self.raw_text,
            "pronoun_only": self.pronoun_only,
        }


@dataclass(slots=True)
class RankedCandidate:
    candidate_id: str
    score: float
    candidate_type: str

    def to_dict(self) -> dict[str, Any]:
        key = "object_id" if self.candidate_type == "object" else "region_id"
        return {key: self.candidate_id, "score": round(self.score, 3)}


@dataclass(slots=True)
class GroundingResult:
    ranked_objects: list[RankedCandidate] = field(default_factory=list)
    ranked_regions: list[RankedCandidate] = field(default_factory=list)

    def best_object(self) -> RankedCandidate | None:
        return self.ranked_objects[0] if self.ranked_objects else None

    def best_region(self) -> RankedCandidate | None:
        return self.ranked_regions[0] if self.ranked_regions else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ranked_objects": [item.to_dict() for item in self.ranked_objects],
            "ranked_regions": [item.to_dict() for item in self.ranked_regions],
        }


@dataclass(slots=True)
class PhasePrediction:
    phase: Phase
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {"phase": self.phase.value, "confidence": round(self.confidence, 3)}


@dataclass(slots=True)
class ConfirmationResult:
    need_confirmation: bool
    question: str = ""
    object_ambiguous: bool = False
    region_ambiguous: bool = False
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "need_confirmation": self.need_confirmation,
            "question": self.question,
            "object_ambiguous": self.object_ambiguous,
            "region_ambiguous": self.region_ambiguous,
            "confidence": round(self.confidence, 3),
        }


@dataclass(slots=True)
class ResolvedTask:
    task_type: str
    object_id: str
    candidate_objects: list[str]
    target_region_id: str
    phase: str
    grasp_type: str
    speed: str
    retry: bool
    confidence: float
    need_confirmation: bool
    question: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "object_id": self.object_id,
            "candidate_objects": self.candidate_objects,
            "target_region_id": self.target_region_id,
            "phase": self.phase,
            "grasp_type": self.grasp_type,
            "speed": self.speed,
            "retry": self.retry,
            "confidence": round(self.confidence, 3),
            "need_confirmation": self.need_confirmation,
            "question": self.question,
        }


def load_json_yaml(path: str | Path) -> dict[str, Any]:
    content = Path(path).read_text(encoding="utf-8").strip()
    return json.loads(content) if content else {}
