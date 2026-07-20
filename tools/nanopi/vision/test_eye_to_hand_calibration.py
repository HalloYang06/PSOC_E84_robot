import importlib.util
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).with_name("eye_to_hand_calibration.py")


def load_module():
    spec = importlib.util.spec_from_file_location("eye_to_hand_calibration", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def rotation_xyz(rx: float, ry: float, rz: float) -> np.ndarray:
    cx, sx = np.cos(rx), np.sin(rx)
    cy, sy = np.cos(ry), np.sin(ry)
    cz, sz = np.cos(rz), np.sin(rz)
    rxm = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], dtype=float)
    rym = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=float)
    rzm = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], dtype=float)
    return rzm @ rym @ rxm


def make_session(*, validation_offset: np.ndarray | None = None) -> tuple[dict, np.ndarray, np.ndarray]:
    rotation = rotation_xyz(0.14, -0.28, 0.37)
    translation = np.array([0.31, -0.12, 0.48], dtype=float)
    camera_points = np.array(
        [
            [-0.16, -0.12, 0.42],
            [0.15, -0.11, 0.44],
            [-0.14, 0.13, 0.46],
            [0.16, 0.12, 0.48],
            [-0.12, -0.09, 0.71],
            [0.13, -0.08, 0.73],
            [-0.11, 0.11, 0.75],
            [0.12, 0.10, 0.77],
            [0.00, -0.14, 0.58],
            [0.00, 0.15, 0.61],
            [-0.17, 0.00, 0.64],
            [0.18, 0.00, 0.67],
            [-0.08, -0.06, 0.52],
            [0.09, -0.05, 0.55],
            [-0.07, 0.07, 0.68],
            [0.08, 0.08, 0.70],
        ],
        dtype=float,
    )
    base_points = (rotation @ camera_points.T).T + translation
    observations = []
    for index, (camera, base) in enumerate(zip(camera_points, base_points), start=1):
        split = "train" if index <= 12 else "validation"
        if split == "validation" and validation_offset is not None:
            base = base + validation_offset
        observations.append(
            {
                "pose_id": f"P{index:02d}",
                "split": split,
                "camera_xyz_m": {"x_m": camera[0], "y_m": camera[1], "z_m": camera[2]},
                "robot_xyz_m": {"x_m": base[0], "y_m": base[1], "z_m": base[2]},
                "sample_count": 10,
                "camera_sample_max_deviation_m": 0.002,
                "source": "synthetic_test",
            }
        )
    observations[5]["robot_xyz_m"] = {"x_m": 0.9, "y_m": -0.8, "z_m": 1.2}
    return (
        {
            "schema_version": "rehab_arm_eye_to_hand_observations_v1",
            "session_id": "synthetic-session",
            "camera_frame_id": "stereo_left_optical_frame",
            "robot_base_frame_id": "base_link",
            "stereo_calibration_id": "stereo-calib-001",
            "active_motor_ids": [4, 5, 6],
            "active_joint_names": ["jian_zongxiang_joint", "zhou_zongxiang_joint", "jian_xuanzhuan_joint"],
            "frozen_joint_names": ["jian_hengxiang_joint", "wanbu_zongxiang_joint", "wanbu_hengxiang_joint"],
            "observations": observations,
        },
        rotation,
        translation,
    )


def test_solver_recovers_base_from_camera_with_outlier_and_validation_set():
    module = load_module()
    session, expected_rotation, expected_translation = make_session()
    result = module.solve_eye_to_hand_session(session, random_seed=7)

    assert result["calibration_state"] == "accepted"
    assert result["transform_direction"] == "base_from_camera"
    assert result["source_stereo_calibration_id"] == "stereo-calib-001"
    assert result["quality"]["train_inlier_count"] == 11
    assert result["quality"]["validation_count"] == 4
    assert result["quality"]["validation_rmse_m"] < 1e-8
    np.testing.assert_allclose(result["rotation_3x3"], expected_rotation, atol=1e-8)
    np.testing.assert_allclose(result["translation_m"], expected_translation, atol=1e-8)


def test_solver_rejects_independent_validation_error():
    module = load_module()
    session, _rotation, _translation = make_session(validation_offset=np.array([0.05, 0.0, 0.0]))
    result = module.solve_eye_to_hand_session(session, random_seed=7)

    assert result["calibration_state"] == "rejected"
    assert "validation_rmse_above_limit" in result["quality"]["reasons"]


def test_solver_rejects_any_motor_set_other_than_4_5_6():
    module = load_module()
    session, _rotation, _translation = make_session()
    session["active_motor_ids"] = [3, 4, 5, 6]
    result = module.solve_eye_to_hand_session(session, random_seed=7)

    assert result["calibration_state"] == "rejected"
    assert "active_motor_set_must_be_4_5_6" in result["quality"]["reasons"]


def test_apply_calibration_transforms_target_and_effector_only_for_matching_stereo_id():
    module = load_module()
    session, rotation, translation = make_session()
    calibration = module.solve_eye_to_hand_session(session, random_seed=7)
    target_camera = {"x_m": 0.04, "y_m": -0.02, "z_m": 0.62}
    effector_camera = {"x_m": -0.03, "y_m": 0.01, "z_m": 0.55}

    evidence = module.build_robot_frame_evidence(
        calibration,
        stereo_calibration_id="stereo-calib-001",
        target_camera_xyz=target_camera,
        end_effector_camera_xyz=effector_camera,
    )

    assert evidence["camera_to_robot_calibrated"] is True
    assert evidence["transform_state"] == "calibrated"
    expected_target = rotation @ np.array([0.04, -0.02, 0.62]) + translation
    np.testing.assert_allclose(
        [evidence["target_3d_robot_frame"][key] for key in ("x_m", "y_m", "z_m")],
        expected_target,
        atol=1e-5,
    )
    mismatch = module.build_robot_frame_evidence(
        calibration,
        stereo_calibration_id="different-stereo-calibration",
        target_camera_xyz=target_camera,
        end_effector_camera_xyz=effector_camera,
    )
    assert mismatch["camera_to_robot_calibrated"] is False
    assert mismatch["transform_state"] == "stereo_calibration_mismatch"
    assert mismatch["target_3d_robot_frame"] is None


def test_capture_observation_requires_true_stereo_effector_depth():
    module = load_module()
    contexts = []
    for index in range(5):
        contexts.append(
            {
                "frame_ts_unix": 100.0 + index,
                "stereo_calibration_id": "stereo-calib-001",
                "end_effector_object": {"label": "gripper_tip", "confidence": 0.91},
                "end_effector_3d_camera_frame": {
                    "x_m": 0.100 + index * 0.0004,
                    "y_m": -0.020 + index * 0.0002,
                    "z_m": 0.600 - index * 0.0003,
                },
                "end_effector_depth_evidence": {
                    "state": "accepted",
                    "reason": "rectified_stereo_match",
                    "method": "independent_left_right_gripper_match",
                },
            }
        )
    observation = module.build_pose_observation(
        contexts,
        pose_id="P01",
        split="train",
        robot_xyz_m={"x_m": 0.3, "y_m": 0.1, "z_m": 0.5},
        joint_angles_deg=[10.0, 20.0, -5.0],
        expected_stereo_calibration_id="stereo-calib-001",
    )
    assert observation["sample_count"] == 5
    assert observation["camera_sample_max_deviation_m"] < 0.002
    assert observation["joint_angles_deg"] == {"4": 10.0, "5": 20.0, "6": -5.0}

    contexts[0]["end_effector_depth_evidence"] = {
        "state": "same_depth_candidate",
        "method": "left_pixel_ray_with_target_depth_assumption",
    }
    try:
        module.build_pose_observation(
            contexts,
            pose_id="P01",
            split="train",
            robot_xyz_m={"x_m": 0.3, "y_m": 0.1, "z_m": 0.5},
            expected_stereo_calibration_id="stereo-calib-001",
        )
    except ValueError as exc:
        assert "independent stereo end-effector depth" in str(exc)
    else:
        raise AssertionError("same-depth demo candidate must not enter hand-eye calibration")


def test_raw_capture_records_three_motor_angles_without_claiming_robot_xyz():
    module = load_module()
    contexts = []
    for index in range(5):
        contexts.append(
            {
                "frame_ts_unix": 200.0 + index,
                "stereo_calibration_id": "stereo-calib-001",
                "end_effector_object": {"label": "gripper_tip", "confidence": 0.93},
                "end_effector_3d_camera_frame": {"x_m": 0.1, "y_m": -0.02, "z_m": 0.6},
                "end_effector_depth_evidence": {
                    "state": "accepted",
                    "method": "independent_left_right_gripper_match",
                },
            }
        )
    observation = module.build_raw_pose_observation(
        contexts,
        pose_id="P01",
        split="train",
        joint_angles_deg=[12.0, 34.0, -8.0],
        expected_stereo_calibration_id="stereo-calib-001",
    )
    assert observation["camera_xyz_m"] == {"x_m": 0.1, "y_m": -0.02, "z_m": 0.6}
    assert observation["joint_angles_deg"] == {"4": 12.0, "5": 34.0, "6": -8.0}
    assert "robot_xyz_m" not in observation
    assert observation["robot_xyz_state"] == "waiting_three_motor_forward_kinematics"


def test_three_motor_fk_uses_visual_zero_protocol_and_model_chain():
    module = load_module()
    visual_qpos = module.visual_qpos_from_motor_angles_deg([0.0, 0.0, 0.0])
    assert np.allclose(visual_qpos, [-0.236, -0.675, 0.0, -1.12, -1.57, 1.05])

    straight_xyz = module.gripper_xyz_from_visual_qpos([0.0] * 6)
    assert np.allclose(straight_xyz, [1.02, 0.0, 0.0], atol=1e-9)


def test_raw_observations_can_be_finalized_with_three_motor_fk():
    module = load_module()
    raw = {
        "pose_id": "P01",
        "joint_angles_deg": {"4": 0.0, "5": 0.0, "6": 0.0},
        "robot_xyz_state": "waiting_three_motor_forward_kinematics",
    }
    finalized = module.finalize_raw_observation_with_fk(raw)

    expected = module.gripper_xyz_from_visual_qpos(module.VISUAL_ZERO)
    assert np.allclose(
        [finalized["robot_xyz_m"][axis] for axis in ("x_m", "y_m", "z_m")],
        expected,
        atol=1e-6,
    )
    assert finalized["robot_xyz_state"] == "derived_from_three_motor_visual_zero_fk"
    assert finalized["source_observation"] == "live_stereo_end_effector_context_raw_joint_sample"
    assert finalized["kinematics_evidence"]["motion_authority"] is False

    raw["active_motor_ids"] = [3, 4, 5]
    try:
        module.finalize_raw_observation_with_fk(raw)
    except ValueError as exc:
        assert "exactly 4,5,6" in str(exc)
    else:
        raise AssertionError("FK must reject observations from a different motor subset")
