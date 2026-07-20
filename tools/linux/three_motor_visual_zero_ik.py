#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import math
from typing import Any


JOINT_NAMES = [
    "jian_hengxiang_joint",
    "jian_zongxiang_joint",
    "jian_xuanzhuan_joint",
    "zhou_zongxiang_joint",
    "wanbu_zongxiang_joint",
    "wanbu_hengxiang_joint",
]
VISUAL_ZERO = [-0.236, -0.675, 0.0, -1.12, -1.57, 1.05]
ACTIVE_INDICES = [1, 3, 2]
HARDWARE_NAMES = ["elbow_lift_joint", "shoulder_abduction_joint", "upper_arm_rotation_joint"]
HARDWARE_LIMITS = [(0.0, 1.8), (0.0, math.radians(150.0)), (-1.2, 1.2)]
SPECS = [
    ((0.0, 0.0, 1.0), (0.24, 0.0, 0.0)),
    ((0.0, 1.0, 0.0), (0.18, 0.0, 0.0)),
    ((1.0, 0.0, 0.0), (0.28, 0.0, 0.0)),
    ((0.0, 1.0, 0.0), (0.12, 0.0, 0.0)),
    ((0.0, 1.0, 0.0), (0.10, 0.0, 0.0)),
    ((0.0, 0.0, 1.0), (0.10, 0.0, 0.0)),
]


def _mat_mul(a, b):
    return [[sum(a[row][k] * b[k][col] for k in range(3)) for col in range(3)] for row in range(3)]


def _mat_vec(a, v):
    return [sum(a[row][col] * v[col] for col in range(3)) for row in range(3)]


def _rotation(axis, angle):
    x, y, z = axis
    c, s, d = math.cos(angle), math.sin(angle), 1.0 - math.cos(angle)
    return [
        [c + x * x * d, x * y * d - z * s, x * z * d + y * s],
        [y * x * d + z * s, c + y * y * d, y * z * d - x * s],
        [z * x * d - y * s, z * y * d + x * s, c + z * z * d],
    ]


def forward_position(qpos: list[float]) -> list[float]:
    rotation = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    point = [0.0, 0.0, 0.0]
    for angle, (axis, offset) in zip(qpos, SPECS):
        rotation = _mat_mul(rotation, _rotation(axis, angle))
        moved = _mat_vec(rotation, offset)
        point = [point[index] + moved[index] for index in range(3)]
    return point


def visual_from_hardware(hardware: list[float]) -> list[float]:
    motor4, motor5, motor6 = hardware
    qpos = list(VISUAL_ZERO)
    qpos[1] = VISUAL_ZERO[1] - motor4
    qpos[3] = VISUAL_ZERO[3] + motor5
    qpos[2] = VISUAL_ZERO[2] + motor6
    return qpos


def hardware_from_visual(qpos: list[float]) -> list[float]:
    return [-(qpos[1] - VISUAL_ZERO[1]), qpos[3] - VISUAL_ZERO[3], qpos[2] - VISUAL_ZERO[2]]


def _clamp_visual(qpos: list[float]) -> list[float]:
    hardware = hardware_from_visual(qpos)
    clamped = [max(low, min(high, value)) for value, (low, high) in zip(hardware, HARDWARE_LIMITS)]
    return visual_from_hardware(clamped)


def _solve_3x3(a, b):
    matrix = [[float(a[row][col]) for col in range(3)] + [float(b[row])] for row in range(3)]
    for pivot in range(3):
        row = max(range(pivot, 3), key=lambda index: abs(matrix[index][pivot]))
        if abs(matrix[row][pivot]) < 1e-10:
            return None
        matrix[pivot], matrix[row] = matrix[row], matrix[pivot]
        scale = matrix[pivot][pivot]
        matrix[pivot] = [value / scale for value in matrix[pivot]]
        for other in range(3):
            if other == pivot:
                continue
            factor = matrix[other][pivot]
            matrix[other] = [matrix[other][col] - factor * matrix[pivot][col] for col in range(4)]
    return [matrix[row][3] for row in range(3)]


def solve(target: dict[str, Any]) -> tuple[list[float], list[float], float]:
    goal = [float(target[key]) for key in ("x_m", "y_m", "z_m")]
    seeds = [
        [m4, m5, m6]
        for m4 in (0.0, 0.45, 0.9, 1.35)
        for m5 in (0.0, 0.65, 1.3, 1.95)
        for m6 in (-0.8, 0.0, 0.8)
    ]
    best = visual_from_hardware([0.0, 0.0, 0.0])
    best_error = math.dist(forward_position(best), goal)
    epsilon = 1e-4
    for seed in seeds:
        qpos = visual_from_hardware(seed)
        for _ in range(100):
            current = forward_position(qpos)
            error = [goal[index] - current[index] for index in range(3)]
            if math.sqrt(sum(value * value for value in error)) <= 0.02:
                break
            columns = []
            for joint_index in ACTIVE_INDICES:
                shifted = list(qpos)
                shifted[joint_index] += epsilon
                moved = forward_position(shifted)
                columns.append([(moved[axis] - current[axis]) / epsilon for axis in range(3)])
            normal = [[sum(column[row] * column[col] for column in columns) for col in range(3)] for row in range(3)]
            for axis in range(3):
                normal[axis][axis] += 0.06 * 0.06
            task_step = _solve_3x3(normal, error)
            if task_step is None:
                break
            updated = list(qpos)
            for joint_index, column in zip(ACTIVE_INDICES, columns):
                updated[joint_index] += 0.65 * sum(column[axis] * task_step[axis] for axis in range(3))
            qpos = _clamp_visual(updated)
        final_error = math.dist(forward_position(qpos), goal)
        if final_error < best_error:
            best, best_error = qpos, final_error
    return best, hardware_from_visual(best), best_error


def build_candidate(
    target: dict[str, Any],
    *,
    source_frame_ts_unix: float,
    source_calibration_id: str,
    semantic_mode: str,
    device_id: str,
) -> dict[str, Any]:
    visual, hardware, error = solve(target)
    quality = "candidate_ready" if error <= 0.03 else ("candidate_approximate" if error <= 0.12 else "candidate_blocked")
    digest = hashlib.sha256(
        json.dumps(
            {
                "device_id": device_id,
                "calibration_id": source_calibration_id,
                "target": {key: round(float(target[key]), 2) for key in ("x_m", "y_m", "z_m")},
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return {
        "schema_version": "rehab_arm_ik_candidate_evidence_v1",
        "candidate_id": "ik_local_" + digest,
        "ik_status": quality,
        "kinematic_profile": "three_motor_visual_zero_v1",
        "active_motor_ids": [4, 5, 6],
        "execution_stage": "shadow_candidate_only",
        "source": "linux_dashboard_calibrated_target_fallback",
        "semantic_mode": semantic_mode,
        "source_frame_ts_unix": source_frame_ts_unix,
        "source_calibration_id": source_calibration_id,
        "target_robot_frame": target,
        "candidate_joint_trajectory": {
            "joint_names": list(JOINT_NAMES),
            "points": [
                {"time_from_start_s": 0.0, "positions_rad": list(VISUAL_ZERO)},
                {"time_from_start_s": 2.0, "positions_rad": [round(value, 4) for value in visual]},
            ],
        },
        "hardware_joint_trajectory_candidate": {
            "joint_names": list(HARDWARE_NAMES),
            "points": [
                {"time_from_start_s": 0.0, "positions_rad": [0.0, 0.0, 0.0]},
                {"time_from_start_s": 2.0, "positions_rad": [round(value, 4) for value in hardware]},
            ],
        },
        "ik_solver_report": {"position_error_m": round(error, 4), "method": "linux_three_motor_visual_zero_dls_v1"},
        "control_boundary": "ik_candidate_evidence_only_not_motion_permission",
    }
