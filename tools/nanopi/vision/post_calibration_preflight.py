#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _numeric_xyz(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    try:
        return all(math.isfinite(float(value[key])) for key in ("x_m", "y_m", "z_m"))
    except (KeyError, TypeError, ValueError):
        return False


def evaluate_post_calibration_readiness(
    calibration: dict[str, Any],
    context: dict[str, Any],
    *,
    now: float,
    max_context_age_s: float = 2.0,
) -> dict[str, Any]:
    blockers: list[str] = []
    calibration_id = str(calibration.get("calibration_id") or "")
    stereo_id = str(context.get("stereo_calibration_id") or "")
    source_stereo_id = str(calibration.get("source_stereo_calibration_id") or "")
    frame_ts = float(context.get("frame_ts_unix") or 0.0)
    context_age_s = max(0.0, now - frame_ts) if frame_ts > 0.0 else float("inf")
    if calibration.get("calibration_state") != "accepted" or not calibration_id:
        blockers.append("active_calibration_not_accepted")
    if not source_stereo_id or source_stereo_id != stereo_id:
        blockers.append("stereo_calibration_id_mismatch")
    if context_age_s > max_context_age_s:
        blockers.append("vision_context_stale")
    if context.get("transform_state") != "calibrated":
        blockers.append("live_context_has_not_loaded_calibration")
    transform = context.get("camera_to_robot_transform") if isinstance(context.get("camera_to_robot_transform"), dict) else {}
    if str(transform.get("calibration_id") or "") != calibration_id:
        blockers.append("live_context_calibration_id_mismatch")
    target_ready = _numeric_xyz(context.get("target_3d_robot_frame"))
    effector_ready = _numeric_xyz(context.get("end_effector_3d_robot_frame"))
    return {
        "schema_version": "rehab_arm_post_calibration_preflight_v1",
        "calibration_ready": not blockers,
        "ready_for_visual_target": not blockers,
        "ready_for_linux_shadow_candidate": not blockers and target_ready and effector_ready,
        "target_robot_frame_ready": target_ready,
        "end_effector_robot_frame_ready": effector_ready,
        "calibration_id": calibration_id,
        "stereo_calibration_id": stereo_id,
        "context_age_s": round(context_age_s, 3) if math.isfinite(context_age_s) else None,
        "blockers": blockers,
        "next_step": (
            "linux_shadow_candidate_ready"
            if not blockers and target_ready and effector_ready
            else ("place_target_and_gripper_in_both_cameras" if not blockers else "fix_calibration_or_context_blockers")
        ),
        "control_boundary": "post_calibration_preflight_only_not_motion_permission",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wait for the live vision loop to load an accepted hand-eye calibration.")
    parser.add_argument("--calibration", default="/home/pi/rehab_arm_calibration/base_from_camera.json")
    parser.add_argument("--context", default="/home/pi/rehab_vla_frames/latest_platform_context.json")
    parser.add_argument("--wait-s", type=float, default=8.0)
    parser.add_argument("--max-context-age-s", type=float, default=2.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    calibration_path = Path(args.calibration).expanduser()
    context_path = Path(args.context).expanduser()
    deadline = time.time() + max(0.0, args.wait_s)
    report: dict[str, Any] = {}
    while True:
        try:
            report = evaluate_post_calibration_readiness(
                _load(calibration_path),
                _load(context_path),
                now=time.time(),
                max_context_age_s=max(0.1, args.max_context_age_s),
            )
        except Exception as exc:
            report = {
                "schema_version": "rehab_arm_post_calibration_preflight_v1",
                "calibration_ready": False,
                "blockers": [f"read_error:{exc}"],
                "control_boundary": "post_calibration_preflight_only_not_motion_permission",
            }
        if report.get("calibration_ready") is True or time.time() >= deadline:
            break
        time.sleep(0.2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("calibration_ready") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
