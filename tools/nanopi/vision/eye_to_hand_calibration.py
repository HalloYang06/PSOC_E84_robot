#!/usr/bin/env python3
"""Solve and apply a fixed-stereo eye-to-hand point calibration.

The transform convention is always::

    p_base = R_base_from_camera @ p_camera + t_base_from_camera

This module only produces coordinate evidence. It does not publish ROS
trajectories, send CAN frames, or grant motion permission.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA_VERSION = "rehab_arm_eye_to_hand_calibration_v1"
SESSION_SCHEMA_VERSION = "rehab_arm_eye_to_hand_observations_v1"
CONTROL_BOUNDARY = "eye_to_hand_transform_evidence_only_not_motion_permission"
ACTIVE_MOTOR_IDS = [4, 5, 6]
ACTIVE_JOINT_NAMES = ["jian_zongxiang_joint", "zhou_zongxiang_joint", "jian_xuanzhuan_joint"]
FROZEN_JOINT_NAMES = ["jian_hengxiang_joint", "wanbu_zongxiang_joint", "wanbu_hengxiang_joint"]


def _xyz_array(value: Any, *, field: str) -> np.ndarray:
    if isinstance(value, dict):
        keys = ("x_m", "y_m", "z_m") if all(key in value for key in ("x_m", "y_m", "z_m")) else ("x", "y", "z")
        try:
            point = np.asarray([value[key] for key in keys], dtype=np.float64)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{field} must contain numeric x_m/y_m/z_m") from exc
    elif isinstance(value, (list, tuple, np.ndarray)) and len(value) == 3:
        point = np.asarray(value, dtype=np.float64)
    else:
        raise ValueError(f"{field} must be a three-element point")
    if point.shape != (3,) or not np.all(np.isfinite(point)):
        raise ValueError(f"{field} must contain three finite values")
    return point


def _xyz_dict(point: np.ndarray) -> dict[str, float]:
    values = np.asarray(point, dtype=np.float64).reshape(3)
    return {"x_m": round(float(values[0]), 6), "y_m": round(float(values[1]), 6), "z_m": round(float(values[2]), 6)}


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _rigid_fit(camera_points: np.ndarray, base_points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    camera = np.asarray(camera_points, dtype=np.float64)
    base = np.asarray(base_points, dtype=np.float64)
    if camera.shape != base.shape or camera.ndim != 2 or camera.shape[1] != 3 or len(camera) < 3:
        raise ValueError("rigid fit requires matching Nx3 arrays with at least three points")
    camera_center = camera.mean(axis=0)
    base_center = base.mean(axis=0)
    camera_zero = camera - camera_center
    base_zero = base - base_center
    if np.linalg.matrix_rank(camera_zero) < 2 or np.linalg.matrix_rank(base_zero) < 2:
        raise ValueError("point set is collinear or degenerate")
    u, _singular, vt = np.linalg.svd(camera_zero.T @ base_zero)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt[-1, :] *= -1
        rotation = vt.T @ u.T
    translation = base_center - rotation @ camera_center
    return rotation, translation


def _errors(camera: np.ndarray, base: np.ndarray, rotation: np.ndarray, translation: np.ndarray) -> np.ndarray:
    predicted = (rotation @ camera.T).T + translation
    return np.linalg.norm(predicted - base, axis=1)


def _pairwise_distance_ratio(camera: np.ndarray, base: np.ndarray) -> float | None:
    camera_distances: list[float] = []
    base_distances: list[float] = []
    for first in range(len(camera)):
        for second in range(first + 1, len(camera)):
            camera_distance = float(np.linalg.norm(camera[first] - camera[second]))
            base_distance = float(np.linalg.norm(base[first] - base[second]))
            if camera_distance > 1e-6 and base_distance > 1e-6:
                camera_distances.append(camera_distance)
                base_distances.append(base_distance)
    if not camera_distances:
        return None
    ratios = np.asarray(base_distances) / np.asarray(camera_distances)
    return float(np.median(ratios))


def _quaternion_xyzw(rotation: np.ndarray) -> list[float]:
    matrix = np.asarray(rotation, dtype=np.float64)
    trace = float(np.trace(matrix))
    if trace > 0:
        scale = np.sqrt(trace + 1.0) * 2.0
        qw = 0.25 * scale
        qx = (matrix[2, 1] - matrix[1, 2]) / scale
        qy = (matrix[0, 2] - matrix[2, 0]) / scale
        qz = (matrix[1, 0] - matrix[0, 1]) / scale
    else:
        index = int(np.argmax(np.diag(matrix)))
        if index == 0:
            scale = np.sqrt(1.0 + matrix[0, 0] - matrix[1, 1] - matrix[2, 2]) * 2.0
            qw = (matrix[2, 1] - matrix[1, 2]) / scale
            qx = 0.25 * scale
            qy = (matrix[0, 1] + matrix[1, 0]) / scale
            qz = (matrix[0, 2] + matrix[2, 0]) / scale
        elif index == 1:
            scale = np.sqrt(1.0 + matrix[1, 1] - matrix[0, 0] - matrix[2, 2]) * 2.0
            qw = (matrix[0, 2] - matrix[2, 0]) / scale
            qx = (matrix[0, 1] + matrix[1, 0]) / scale
            qy = 0.25 * scale
            qz = (matrix[1, 2] + matrix[2, 1]) / scale
        else:
            scale = np.sqrt(1.0 + matrix[2, 2] - matrix[0, 0] - matrix[1, 1]) * 2.0
            qw = (matrix[1, 0] - matrix[0, 1]) / scale
            qx = (matrix[0, 2] + matrix[2, 0]) / scale
            qy = (matrix[1, 2] + matrix[2, 1]) / scale
            qz = 0.25 * scale
    quaternion = np.asarray([qx, qy, qz, qw], dtype=np.float64)
    quaternion /= np.linalg.norm(quaternion)
    return [round(float(value), 10) for value in quaternion]


def _ransac_fit(
    camera: np.ndarray,
    base: np.ndarray,
    *,
    threshold_m: float,
    iterations: int,
    random_seed: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if len(camera) < 3:
        raise ValueError("at least three train points are required")
    generator = np.random.default_rng(random_seed)
    best_inliers: np.ndarray | None = None
    best_rmse = float("inf")
    for _ in range(max(1, iterations)):
        indices = generator.choice(len(camera), size=3, replace=False)
        try:
            rotation, translation = _rigid_fit(camera[indices], base[indices])
        except ValueError:
            continue
        errors = _errors(camera, base, rotation, translation)
        inliers = errors <= threshold_m
        count = int(inliers.sum())
        if count < 3:
            continue
        rmse = float(np.sqrt(np.mean(np.square(errors[inliers]))))
        if best_inliers is None or count > int(best_inliers.sum()) or (count == int(best_inliers.sum()) and rmse < best_rmse):
            best_inliers = inliers
            best_rmse = rmse
    if best_inliers is None:
        raise ValueError("RANSAC could not find a non-degenerate rigid transform")
    rotation, translation = _rigid_fit(camera[best_inliers], base[best_inliers])
    refined_errors = _errors(camera, base, rotation, translation)
    refined_inliers = refined_errors <= threshold_m
    if int(refined_inliers.sum()) >= 3 and not np.array_equal(refined_inliers, best_inliers):
        rotation, translation = _rigid_fit(camera[refined_inliers], base[refined_inliers])
        best_inliers = refined_inliers
    return rotation, translation, best_inliers


def solve_eye_to_hand_session(
    session: dict[str, Any],
    *,
    random_seed: int = 42,
    ransac_iterations: int = 1000,
    ransac_threshold_m: float = 0.015,
    min_train_poses: int = 8,
    min_validation_poses: int = 3,
    min_train_inlier_ratio: float = 0.75,
    min_axis_span_m: float = 0.04,
    max_train_rmse_m: float = 0.012,
    max_validation_rmse_m: float = 0.020,
    max_validation_error_m: float = 0.035,
    min_distance_ratio: float = 0.90,
    max_distance_ratio: float = 1.10,
) -> dict[str, Any]:
    if session.get("schema_version") != SESSION_SCHEMA_VERSION:
        raise ValueError(f"session.schema_version must be {SESSION_SCHEMA_VERSION}")
    observations = session.get("observations")
    if not isinstance(observations, list):
        raise ValueError("session.observations must be a list")

    train_camera: list[np.ndarray] = []
    train_base: list[np.ndarray] = []
    validation_camera: list[np.ndarray] = []
    validation_base: list[np.ndarray] = []
    train_pose_ids: list[str] = []
    for observation in observations:
        if not isinstance(observation, dict):
            raise ValueError("each observation must be an object")
        camera_point = _xyz_array(observation.get("camera_xyz_m"), field="camera_xyz_m")
        base_point = _xyz_array(observation.get("robot_xyz_m"), field="robot_xyz_m")
        split = str(observation.get("split") or "train")
        if split == "validation":
            validation_camera.append(camera_point)
            validation_base.append(base_point)
        elif split == "train":
            train_camera.append(camera_point)
            train_base.append(base_point)
            train_pose_ids.append(str(observation.get("pose_id") or f"train-{len(train_pose_ids) + 1}"))
        else:
            raise ValueError("observation.split must be train or validation")

    if len(train_camera) < 3:
        raise ValueError("at least three train observations are required to compute a candidate")
    train_camera_array = np.vstack(train_camera)
    train_base_array = np.vstack(train_base)
    rotation, translation, inlier_mask = _ransac_fit(
        train_camera_array,
        train_base_array,
        threshold_m=ransac_threshold_m,
        iterations=ransac_iterations,
        random_seed=random_seed,
    )
    train_errors = _errors(train_camera_array, train_base_array, rotation, translation)
    train_inlier_errors = train_errors[inlier_mask]
    validation_camera_array = np.vstack(validation_camera) if validation_camera else np.empty((0, 3), dtype=np.float64)
    validation_base_array = np.vstack(validation_base) if validation_base else np.empty((0, 3), dtype=np.float64)
    validation_errors = (
        _errors(validation_camera_array, validation_base_array, rotation, translation)
        if len(validation_camera_array)
        else np.asarray([], dtype=np.float64)
    )
    coverage = np.ptp(train_base_array[inlier_mask], axis=0)
    train_rmse = float(np.sqrt(np.mean(np.square(train_inlier_errors))))
    validation_rmse = float(np.sqrt(np.mean(np.square(validation_errors)))) if len(validation_errors) else None
    validation_max = float(np.max(validation_errors)) if len(validation_errors) else None
    inlier_ratio = float(np.mean(inlier_mask))
    distance_ratio = _pairwise_distance_ratio(train_camera_array[inlier_mask], train_base_array[inlier_mask])
    orthogonality_error = float(np.linalg.norm(rotation.T @ rotation - np.eye(3), ord="fro"))
    determinant = float(np.linalg.det(rotation))

    reasons: list[str] = []
    if session.get("active_motor_ids") != ACTIVE_MOTOR_IDS:
        reasons.append("active_motor_set_must_be_4_5_6")
    if len(train_camera_array) < min_train_poses:
        reasons.append("train_pose_count_below_minimum")
    if len(validation_camera_array) < min_validation_poses:
        reasons.append("validation_pose_count_below_minimum")
    if inlier_ratio < min_train_inlier_ratio:
        reasons.append("train_inlier_ratio_below_minimum")
    if train_rmse > max_train_rmse_m:
        reasons.append("train_rmse_above_limit")
    if validation_rmse is None or validation_rmse > max_validation_rmse_m:
        reasons.append("validation_rmse_above_limit")
    if validation_max is None or validation_max > max_validation_error_m:
        reasons.append("validation_max_error_above_limit")
    if np.any(coverage < min_axis_span_m):
        reasons.append("robot_workspace_axis_span_below_minimum")
    if distance_ratio is None or not min_distance_ratio <= distance_ratio <= max_distance_ratio:
        reasons.append("camera_robot_distance_scale_mismatch")
    if orthogonality_error > 1e-6 or abs(determinant - 1.0) > 1e-6:
        reasons.append("rotation_matrix_invalid")

    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = rotation
    matrix[:3, 3] = translation
    digest_input = json.dumps(
        {
            "stereo": session.get("stereo_calibration_id"),
            "matrix": np.round(matrix, 10).tolist(),
            "train_pose_ids": train_pose_ids,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    calibration_id = f"eye-to-hand-{hashlib.sha256(digest_input).hexdigest()[:16]}"
    return {
        "schema_version": SCHEMA_VERSION,
        "calibration_id": calibration_id,
        "calibration_state": "accepted" if not reasons else "rejected",
        "calibration_kind": "fixed_stereo_eye_to_hand_point_correspondence",
        "created_ts_unix": time.time(),
        "session_id": str(session.get("session_id") or ""),
        "camera_frame_id": str(session.get("camera_frame_id") or "stereo_left_optical_frame"),
        "robot_base_frame_id": str(session.get("robot_base_frame_id") or "base_link"),
        "source_stereo_calibration_id": str(session.get("stereo_calibration_id") or ""),
        "transform_direction": "base_from_camera",
        "rotation_3x3": np.round(rotation, 10).tolist(),
        "translation_m": np.round(translation, 10).tolist(),
        "quaternion_xyzw": _quaternion_xyzw(rotation),
        "matrix_4x4": np.round(matrix, 10).tolist(),
        "quality": {
            "state": "accepted" if not reasons else "rejected",
            "reasons": reasons,
            "train_pose_count": int(len(train_camera_array)),
            "train_inlier_count": int(inlier_mask.sum()),
            "train_inlier_pose_ids": [pose_id for pose_id, keep in zip(train_pose_ids, inlier_mask.tolist()) if keep],
            "train_outlier_pose_ids": [pose_id for pose_id, keep in zip(train_pose_ids, inlier_mask.tolist()) if not keep],
            "train_inlier_ratio": round(inlier_ratio, 6),
            "train_rmse_m": round(train_rmse, 6),
            "train_median_error_m": round(float(np.median(train_inlier_errors)), 6),
            "train_max_error_m": round(float(np.max(train_inlier_errors)), 6),
            "validation_count": int(len(validation_errors)),
            "validation_rmse_m": round(validation_rmse, 6) if validation_rmse is not None else None,
            "validation_median_error_m": round(float(np.median(validation_errors)), 6) if len(validation_errors) else None,
            "validation_max_error_m": round(validation_max, 6) if validation_max is not None else None,
            "robot_workspace_span_m": [round(float(value), 6) for value in coverage],
            "median_pairwise_distance_ratio_base_over_camera": round(distance_ratio, 6) if distance_ratio is not None else None,
            "rotation_determinant": round(determinant, 10),
            "rotation_orthogonality_error": round(orthogonality_error, 12),
            "gates": {
                "ransac_threshold_m": ransac_threshold_m,
                "min_train_poses": min_train_poses,
                "min_validation_poses": min_validation_poses,
                "min_train_inlier_ratio": min_train_inlier_ratio,
                "min_axis_span_m": min_axis_span_m,
                "max_train_rmse_m": max_train_rmse_m,
                "max_validation_rmse_m": max_validation_rmse_m,
                "max_validation_error_m": max_validation_error_m,
                "pairwise_distance_ratio_range": [min_distance_ratio, max_distance_ratio],
            },
        },
        "warning": "Point calibration maps XYZ only. Grasp orientation requires a separately validated orientation/marker calibration.",
        "control_boundary": CONTROL_BOUNDARY,
    }


def _transform_point(calibration: dict[str, Any], point: Any) -> dict[str, float]:
    matrix = np.asarray(calibration.get("matrix_4x4"), dtype=np.float64)
    if matrix.shape != (4, 4) or not np.all(np.isfinite(matrix)):
        raise ValueError("calibration.matrix_4x4 must be finite 4x4")
    camera_point = _xyz_array(point, field="camera point")
    base_point = matrix[:3, :3] @ camera_point + matrix[:3, 3]
    return _xyz_dict(base_point)


def build_robot_frame_evidence(
    calibration: dict[str, Any] | None,
    *,
    stereo_calibration_id: str,
    target_camera_xyz: Any = None,
    end_effector_camera_xyz: Any = None,
) -> dict[str, Any]:
    base = {
        "camera_to_robot_transform": None,
        "camera_to_robot_calibrated": False,
        "transform_state": "waiting_calibration",
        "target_3d_robot_frame": None,
        "end_effector_3d_robot_frame": None,
        "robot_frame_delta_to_target": None,
    }
    if not isinstance(calibration, dict):
        return base
    if calibration.get("calibration_state") != "accepted":
        return {**base, "transform_state": "calibration_rejected"}
    source_stereo_id = str(calibration.get("source_stereo_calibration_id") or "")
    if not source_stereo_id or source_stereo_id != str(stereo_calibration_id or ""):
        return {**base, "transform_state": "stereo_calibration_mismatch"}
    target_base = _transform_point(calibration, target_camera_xyz) if target_camera_xyz else None
    effector_base = _transform_point(calibration, end_effector_camera_xyz) if end_effector_camera_xyz else None
    delta = None
    if target_base and effector_base:
        target_array = _xyz_array(target_base, field="target base point")
        effector_array = _xyz_array(effector_base, field="end effector base point")
        difference = target_array - effector_array
        delta = {
            "dx_m": round(float(difference[0]), 6),
            "dy_m": round(float(difference[1]), 6),
            "dz_m": round(float(difference[2]), 6),
            "distance_m": round(float(np.linalg.norm(difference)), 6),
        }
    transform = {
        "schema_version": SCHEMA_VERSION,
        "calibration_id": calibration.get("calibration_id"),
        "state": "accepted",
        "camera_frame_id": calibration.get("camera_frame_id"),
        "robot_base_frame_id": calibration.get("robot_base_frame_id"),
        "source_stereo_calibration_id": source_stereo_id,
        "transform_direction": "base_from_camera",
        "matrix_4x4": calibration.get("matrix_4x4"),
        "quality": calibration.get("quality"),
        "control_boundary": CONTROL_BOUNDARY,
    }
    return {
        "camera_to_robot_transform": transform,
        "camera_to_robot_calibrated": True,
        "transform_state": "calibrated",
        "target_3d_robot_frame": target_base,
        "end_effector_3d_robot_frame": effector_base,
        "robot_frame_delta_to_target": delta,
    }


def load_calibration(path_text: str) -> dict[str, Any] | None:
    if not path_text:
        return None
    path = Path(path_text).expanduser()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _validated_effector_sample(context: dict[str, Any], expected_stereo_calibration_id: str, min_confidence: float) -> np.ndarray:
    stereo_id = str(context.get("stereo_calibration_id") or "")
    if stereo_id != expected_stereo_calibration_id:
        raise ValueError("context stereo_calibration_id does not match the session")
    evidence = context.get("end_effector_depth_evidence") if isinstance(context.get("end_effector_depth_evidence"), dict) else {}
    method = str(evidence.get("method") or "")
    independent_stereo = "independent" in method and ("stereo" in method or "left_right" in method)
    if evidence.get("state") != "accepted" or not independent_stereo:
        raise ValueError("hand-eye capture requires independent stereo end-effector depth")
    end_effector = context.get("end_effector_object") if isinstance(context.get("end_effector_object"), dict) else {}
    confidence = float(end_effector.get("confidence") or 0.0)
    if confidence < min_confidence:
        raise ValueError("end-effector confidence is below the hand-eye capture gate")
    return _xyz_array(context.get("end_effector_3d_camera_frame"), field="end_effector_3d_camera_frame")


def build_pose_observation(
    contexts: list[dict[str, Any]],
    *,
    pose_id: str,
    split: str,
    robot_xyz_m: Any,
    joint_angles_deg: Any = None,
    expected_stereo_calibration_id: str,
    min_confidence: float = 0.70,
    max_camera_spread_m: float = 0.010,
) -> dict[str, Any]:
    observation = build_raw_pose_observation(
        contexts,
        pose_id=pose_id,
        split=split,
        joint_angles_deg=joint_angles_deg,
        expected_stereo_calibration_id=expected_stereo_calibration_id,
        min_confidence=min_confidence,
        max_camera_spread_m=max_camera_spread_m,
    )
    observation["robot_xyz_m"] = _xyz_dict(_xyz_array(robot_xyz_m, field="robot_xyz_m"))
    observation["source"] = "live_stereo_end_effector_context_with_robot_fk"
    return observation


def build_raw_pose_observation(
    contexts: list[dict[str, Any]],
    *,
    pose_id: str,
    split: str,
    joint_angles_deg: Any,
    expected_stereo_calibration_id: str,
    min_confidence: float = 0.70,
    max_camera_spread_m: float = 0.010,
) -> dict[str, Any]:
    if split not in {"train", "validation"}:
        raise ValueError("split must be train or validation")
    if len(contexts) < 5:
        raise ValueError("at least five fresh stereo contexts are required per pose")
    frame_timestamps: list[float] = []
    points: list[np.ndarray] = []
    for context in contexts:
        if not isinstance(context, dict):
            raise ValueError("each context must be an object")
        points.append(_validated_effector_sample(context, expected_stereo_calibration_id, min_confidence))
        frame_timestamps.append(float(context.get("frame_ts_unix") or 0.0))
    if len(set(frame_timestamps)) != len(frame_timestamps):
        raise ValueError("hand-eye pose samples must come from distinct fresh frames")
    camera_samples = np.vstack(points)
    median = np.median(camera_samples, axis=0)
    deviations = np.linalg.norm(camera_samples - median, axis=1)
    max_deviation = float(np.max(deviations))
    if max_deviation > max_camera_spread_m:
        raise ValueError("end-effector stereo point is not stable enough for hand-eye capture")
    angles = [float(value) for value in joint_angles_deg]
    if len(angles) != 3 or not np.all(np.isfinite(angles)):
        raise ValueError("joint_angles_deg must contain finite motor 4/5/6 angles")
    return {
        "pose_id": pose_id,
        "split": split,
        "camera_xyz_m": _xyz_dict(median),
        "active_motor_ids": list(ACTIVE_MOTOR_IDS),
        "active_joint_names": list(ACTIVE_JOINT_NAMES),
        "joint_angles_deg": {
            str(motor_id): round(angle, 6) for motor_id, angle in zip(ACTIVE_MOTOR_IDS, angles)
        },
        "sample_count": len(contexts),
        "camera_sample_max_deviation_m": round(max_deviation, 6),
        "camera_sample_median_deviation_m": round(float(np.median(deviations)), 6),
        "frame_ts_range_unix": [min(frame_timestamps), max(frame_timestamps)],
        "end_effector_depth_method": "independent_left_right_gripper_match",
        "source": "live_stereo_end_effector_context_raw_joint_sample",
        "robot_xyz_state": "waiting_three_motor_forward_kinematics",
        "control_boundary": CONTROL_BOUNDARY,
    }


def _parse_xyz_text(text: str) -> dict[str, float]:
    values = [float(item.strip()) for item in text.split(",") if item.strip()]
    if len(values) != 3:
        raise ValueError("XYZ must contain three comma-separated values in meters")
    return {"x_m": values[0], "y_m": values[1], "z_m": values[2]}


def _parse_joint_angles_text(text: str) -> list[float]:
    values = [float(item.strip()) for item in text.split(",") if item.strip()]
    if len(values) != 3 or not np.all(np.isfinite(values)):
        raise ValueError("joint angles must be motor 4,5,6 as three comma-separated degrees")
    return values


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _capture_contexts(path: Path, *, samples: int, timeout_s: float, interval_s: float, stereo_id: str, min_confidence: float) -> list[dict[str, Any]]:
    deadline = time.time() + timeout_s
    contexts: list[dict[str, Any]] = []
    seen_timestamps: set[float] = set()
    last_error = "no context observed"
    while time.time() < deadline and len(contexts) < samples:
        try:
            context = _load_json(path)
            timestamp = float(context.get("frame_ts_unix") or 0.0)
            if timestamp not in seen_timestamps:
                _validated_effector_sample(context, stereo_id, min_confidence)
                contexts.append(context)
                seen_timestamps.add(timestamp)
        except Exception as exc:
            last_error = str(exc)
        time.sleep(max(0.02, interval_s))
    if len(contexts) < samples:
        raise RuntimeError(f"collected {len(contexts)}/{samples} valid contexts: {last_error}")
    return contexts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fixed-stereo eye-to-hand point calibration for rehab-arm.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    initialize = subparsers.add_parser("init", help="Create an empty calibration observation session.")
    initialize.add_argument("--output", required=True)
    initialize.add_argument("--session-id", default="")
    initialize.add_argument("--stereo-calibration-id", required=True)
    initialize.add_argument("--camera-frame-id", default="stereo_left_optical_frame")
    initialize.add_argument("--robot-base-frame-id", default="base_link")

    capture = subparsers.add_parser("capture", help="Capture one stable robot pose from a live stereo context file.")
    capture.add_argument("--session", required=True)
    capture.add_argument("--context-json", required=True)
    capture.add_argument("--pose-id", required=True)
    capture.add_argument("--split", choices=["train", "validation"], default="train")
    capture.add_argument("--robot-xyz", required=True, help="Authoritative gripper-tip XYZ in base_link, meters.")
    capture.add_argument("--joint-angles-deg", required=True, help="Measured motor 4,5,6 angles in degrees.")
    capture.add_argument("--samples", type=int, default=10)
    capture.add_argument("--timeout-s", type=float, default=12.0)
    capture.add_argument("--interval-s", type=float, default=0.10)
    capture.add_argument("--min-confidence", type=float, default=0.70)
    capture.add_argument("--max-camera-spread-m", type=float, default=0.010)
    capture.add_argument("--replace", action="store_true")

    capture_raw = subparsers.add_parser("capture-raw", help="Capture camera XYZ with measured motor 4/5/6 angles before FK is available.")
    capture_raw.add_argument("--session", required=True)
    capture_raw.add_argument("--context-json", required=True)
    capture_raw.add_argument("--pose-id", required=True)
    capture_raw.add_argument("--split", choices=["train", "validation"], default="train")
    capture_raw.add_argument("--joint-angles-deg", required=True, help="Measured motor 4,5,6 angles in degrees.")
    capture_raw.add_argument("--samples", type=int, default=10)
    capture_raw.add_argument("--timeout-s", type=float, default=12.0)
    capture_raw.add_argument("--interval-s", type=float, default=0.10)
    capture_raw.add_argument("--min-confidence", type=float, default=0.70)
    capture_raw.add_argument("--max-camera-spread-m", type=float, default=0.010)
    capture_raw.add_argument("--replace", action="store_true")

    solve = subparsers.add_parser("solve", help="Solve and validate base_from_camera from a session.")
    solve.add_argument("--session", required=True)
    solve.add_argument("--output", required=True)
    solve.add_argument("--random-seed", type=int, default=42)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "init":
        now = time.time()
        payload = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "session_id": args.session_id or time.strftime("eye-to-hand-%Y%m%d-%H%M%S", time.localtime(now)),
            "created_ts_unix": now,
            "camera_frame_id": args.camera_frame_id,
            "robot_base_frame_id": args.robot_base_frame_id,
            "stereo_calibration_id": args.stereo_calibration_id,
            "active_motor_ids": list(ACTIVE_MOTOR_IDS),
            "active_joint_names": list(ACTIVE_JOINT_NAMES),
            "frozen_joint_names": list(FROZEN_JOINT_NAMES),
            "observations": [],
            "control_boundary": CONTROL_BOUNDARY,
        }
        _write_json_atomic(Path(args.output).expanduser(), payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.command in {"capture", "capture-raw"}:
        session_path = Path(args.session).expanduser()
        session = _load_json(session_path)
        contexts = _capture_contexts(
            Path(args.context_json).expanduser(),
            samples=max(5, args.samples),
            timeout_s=max(1.0, args.timeout_s),
            interval_s=max(0.02, args.interval_s),
            stereo_id=str(session.get("stereo_calibration_id") or ""),
            min_confidence=args.min_confidence,
        )
        common = {
            "pose_id": args.pose_id,
            "split": args.split,
            "joint_angles_deg": _parse_joint_angles_text(args.joint_angles_deg),
            "expected_stereo_calibration_id": str(session.get("stereo_calibration_id") or ""),
            "min_confidence": args.min_confidence,
            "max_camera_spread_m": args.max_camera_spread_m,
        }
        if args.command == "capture":
            observation = build_pose_observation(contexts, robot_xyz_m=_parse_xyz_text(args.robot_xyz), **common)
        else:
            observation = build_raw_pose_observation(contexts, **common)
        observations = session.setdefault("observations", [])
        existing = [index for index, item in enumerate(observations) if isinstance(item, dict) and item.get("pose_id") == args.pose_id]
        if existing and not args.replace:
            raise SystemExit(f"pose_id {args.pose_id} already exists; use --replace to recapture")
        for index in reversed(existing):
            del observations[index]
        observations.append(observation)
        _write_json_atomic(session_path, session)
        print(json.dumps(observation, ensure_ascii=False, indent=2))
        return 0
    if args.command == "solve":
        session = _load_json(Path(args.session).expanduser())
        calibration = solve_eye_to_hand_session(session, random_seed=args.random_seed)
        _write_json_atomic(Path(args.output).expanduser(), calibration)
        print(json.dumps(calibration, ensure_ascii=False, indent=2))
        return 0 if calibration["calibration_state"] == "accepted" else 2
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
