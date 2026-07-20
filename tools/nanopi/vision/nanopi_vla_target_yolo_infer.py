#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import onnxruntime as ort


COCO_TARGET_CLASSES = {
    39: ("target_bottle", "bottle"),
    41: ("target_cup", "cup"),
}

PROJECT_SINGLE_CLASS_CHANNELS = {5, 6}


def nms_items(items: list[dict], iou_threshold: float = 0.45) -> list[dict]:
    if not items:
        return []
    order = sorted(range(len(items)), key=lambda index: float(items[index]["confidence"]), reverse=True)
    kept: list[int] = []
    while order:
        current = order.pop(0)
        kept.append(current)
        order = [index for index in order if bbox_iou(items[current]["bbox_xywh"], items[index]["bbox_xywh"]) <= iou_threshold]
    return [items[index] for index in kept]


def bbox_iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, aw, ah = [float(v) for v in a]
    bx1, by1, bw, bh = [float(v) for v in b]
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def load_tensor(tensor_path: Path, imgsz: int) -> np.ndarray | None:
    if not tensor_path.is_file():
        return None
    try:
        return np.fromfile(tensor_path, dtype=np.float32).reshape(1, 3, imgsz, imgsz)
    except Exception:
        return None


def detect(tensor_path: Path, model_path: Path, conf: float, imgsz: int, frame_w: int, frame_h: int) -> dict:
    min_width = float(os.environ.get("REHAB_TARGET_MIN_WIDTH_PX", "40"))
    min_height = float(os.environ.get("REHAB_TARGET_MIN_HEIGHT_PX", "50"))
    single_class_label = os.environ.get("REHAB_TARGET_SINGLE_CLASS_LABEL", "").strip()
    quality_detector = "project_single_class_target_detector" if single_class_label else "pretrained_yolo_coco_target_detector"
    tensor = load_tensor(tensor_path, imgsz)
    if tensor is None:
        return {
            "target": None,
            "quality_gate": {
                "schema_version": "target_quality_gate_v2",
                "state": "missing_target_tensor",
                "detector": quality_detector,
                "control_boundary": "target_quality_gate_only_not_motion_permission",
            },
        }
    if not model_path.is_file():
        return {
            "target": None,
            "quality_gate": {
                "schema_version": "target_quality_gate_v2",
                "state": "target_model_missing",
                "model_path": str(model_path),
                "detector": quality_detector,
                "control_boundary": "target_quality_gate_only_not_motion_permission",
            },
        }
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name
    output = session.run([output_name], {input_name: tensor})[0]
    raw = np.squeeze(np.asarray(output))
    if raw.ndim != 2:
        return {
            "target": None,
            "quality_gate": {
                "schema_version": "target_quality_gate_v2",
                "state": "unexpected_yolo_output",
                "output_shape": list(np.asarray(output).shape),
                "detector": quality_detector,
                "control_boundary": "target_quality_gate_only_not_motion_permission",
            },
        }
    if raw.shape[0] in {84, 85, *PROJECT_SINGLE_CLASS_CHANNELS} and raw.shape[1] > raw.shape[0]:
        raw = raw.T
    scale_x = frame_w / float(imgsz)
    scale_y = frame_h / float(imgsz)
    candidates: list[dict] = []
    rejected_low_conf = 0
    rejected_too_small = 0
    for row in raw:
        if len(row) in PROJECT_SINGLE_CLASS_CHANNELS:
            obj_conf = 1.0
            confidence = float(row[4])
            label = os.environ.get("REHAB_TARGET_SINGLE_CLASS_LABEL", "target_bottle")
            coco_label = os.environ.get("REHAB_TARGET_SINGLE_CLASS_COCO_LABEL", "project_custom")
            detector_family = "project_single_class_target_detector"
        elif len(row) < 84:
            continue
        else:
            if len(row) >= 85:
                obj_conf = float(row[4])
                scores = row[5:85]
                detector_family = "yolov5_coco_target_detector"
            else:
                obj_conf = 1.0
                scores = row[4:84]
                detector_family = "yolov8_or_yolo11_coco_target_detector"
            class_id = int(np.argmax(scores))
            if class_id not in COCO_TARGET_CLASSES:
                continue
            confidence = obj_conf * float(scores[class_id])
            label, coco_label = COCO_TARGET_CLASSES[class_id]
        if confidence < conf:
            rejected_low_conf += 1
            continue
        cx, cy, bw, bh = [float(value) for value in row[:4]]
        x = max(0.0, min(float(frame_w - 1), (cx - bw / 2.0) * scale_x))
        y = max(0.0, min(float(frame_h - 1), (cy - bh / 2.0) * scale_y))
        width = max(1.0, min(float(frame_w) - x, bw * scale_x))
        height = max(1.0, min(float(frame_h) - y, bh * scale_y))
        if width < min_width or height < min_height:
            rejected_too_small += 1
            continue
        candidates.append(
            {
                "label": label,
                "coco_label": coco_label,
                "confidence": round(confidence, 4),
                "bbox_xywh": [round(x, 2), round(y, 2), round(width, 2), round(height, 2)],
                "center_px": [round(x + width / 2.0, 2), round(y + height / 2.0, 2)],
                "source": detector_family,
                "model_path": str(model_path),
            }
        )
    accepted = nms_items(candidates)
    accepted.sort(key=lambda item: float(item.get("confidence", 0.0)), reverse=True)
    target = accepted[0] if accepted else None
    return {
        "target": target,
        "accepted_candidates": accepted[:8],
        "quality_gate": {
            "schema_version": "target_quality_gate_v2",
            "state": "candidate_accepted" if target else "no_yolo_cup_or_bottle",
            "detector": quality_detector,
            "model_path": str(model_path),
            "accepted_count": len(accepted),
            "candidate_count": len(candidates),
            "rejected_low_confidence": rejected_low_conf,
            "rejected_too_small": rejected_too_small,
            "min_confidence": conf,
            "min_size_px": [min_width, min_height],
            "target_classes": ["target_bottle", "target_cup"],
            "control_boundary": "target_quality_gate_only_not_motion_permission",
        },
    }


def main() -> int:
    out_dir = Path(os.environ.get("REHAB_VLA_OUT_DIR", "/home/pi/rehab_vla_cpp_probe"))
    tensor_path = Path(os.environ.get("REHAB_TARGET_TENSOR", str(out_dir / "latest_target_tensor_chw_fp32.bin")))
    model_path = Path(os.environ.get("REHAB_TARGET_ONNX", "/home/pi/rehab_arm_models/yolo/yolov5n.onnx"))
    conf = float(os.environ.get("REHAB_TARGET_CONF", "0.30"))
    imgsz = int(os.environ.get("REHAB_TARGET_IMGSZ", "640"))
    frame_w = int(os.environ.get("REHAB_TARGET_FRAME_WIDTH", "640"))
    frame_h = int(os.environ.get("REHAB_TARGET_FRAME_HEIGHT", "480"))
    print(json.dumps(detect(tensor_path, model_path, conf, imgsz, frame_w, frame_h), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
