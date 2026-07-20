#!/usr/bin/env python3
"""Stage platform VLA IK candidates through MuJoCo before formal hardware ROS.

The agent never sends CAN or motor-private frames. Hardware publication is
disabled unless both explicit command-line confirmations are present.
"""

from __future__ import annotations

import argparse
import json
import math
import time
import urllib.request
from typing import Any


SIM_TOPIC = "/sim/medical_arm/joint_trajectory"
SIM_STATE_TOPIC = "/sim/medical_arm/joint_states"
HARDWARE_TOPIC = "/arm_controller/joint_trajectory"
SAFETY_TOPIC = "/rehab_arm/safety_state"
CONTROL_BOUNDARY = "linux_vla_execution_agent_requires_shadow_and_m33"


def _finite_positions(point: dict[str, Any], count: int) -> list[float]:
    values = point.get("positions_rad")
    if not isinstance(values, list) or len(values) != count:
        raise ValueError("trajectory positions must match joint_names")
    positions = [float(value) for value in values]
    if not all(math.isfinite(value) for value in positions):
        raise ValueError("trajectory positions must be finite")
    return positions


def validate_candidate(candidate: dict[str, Any], *, now: float, max_age_s: float) -> dict[str, Any]:
    if candidate.get("schema_version") != "rehab_arm_ik_candidate_evidence_v1":
        raise ValueError("unexpected candidate schema")
    if candidate.get("control_boundary") != "ik_candidate_evidence_only_not_motion_permission":
        raise ValueError("candidate control boundary is invalid")
    if candidate.get("kinematic_profile") != "three_motor_visual_zero_v1":
        raise ValueError("only the three-motor visual-zero profile is accepted")
    if candidate.get("active_motor_ids") != [4, 5, 6]:
        raise ValueError("active motor set must be exactly 4,5,6")
    if candidate.get("ik_status") not in {"candidate_ready", "candidate_approximate"}:
        raise ValueError("IK candidate is not ready for shadow review")
    if candidate.get("semantic_mode") not in {"fetch_object", "vision_servo"}:
        raise ValueError("semantic mode does not permit VLA motion review")
    if not str(candidate.get("source_calibration_id") or ""):
        raise ValueError("candidate is missing eye-to-hand calibration provenance")
    source_ts = float(candidate.get("source_frame_ts_unix") or 0.0)
    if source_ts <= 0.0 or now - source_ts > max_age_s or source_ts - now > 1.0:
        raise ValueError("candidate camera frame is stale or clock-invalid")
    visual = candidate.get("candidate_joint_trajectory")
    hardware = candidate.get("hardware_joint_trajectory_candidate")
    if not isinstance(visual, dict) or not isinstance(hardware, dict):
        raise ValueError("candidate is missing visual or hardware trajectory")
    visual_names = visual.get("joint_names")
    hardware_names = hardware.get("joint_names")
    if not isinstance(visual_names, list) or len(visual_names) != 6:
        raise ValueError("visual trajectory must contain six model joints")
    if hardware_names != ["elbow_lift_joint", "shoulder_abduction_joint", "upper_arm_rotation_joint"]:
        raise ValueError("hardware trajectory must use the established motor 4/5/6 joint mapping")
    visual_points = visual.get("points")
    hardware_points = hardware.get("points")
    if not isinstance(visual_points, list) or len(visual_points) < 2:
        raise ValueError("visual trajectory requires start and target points")
    if not isinstance(hardware_points, list) or len(hardware_points) < 2:
        raise ValueError("hardware trajectory requires start and target points")
    visual_target = _finite_positions(visual_points[-1], len(visual_names))
    hardware_target = _finite_positions(hardware_points[-1], len(hardware_names))
    return {
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "visual_joint_names": list(visual_names),
        "visual_target": visual_target,
        "hardware_joint_names": list(hardware_names),
        "hardware_target": hardware_target,
        "duration_s": max(0.2, float(visual_points[-1].get("time_from_start_s") or 2.0)),
        "ik_status": candidate["ik_status"],
    }


def _request_json(url: str, *, payload: dict[str, Any] | None = None, timeout_s: float = 3.0) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        result = json.loads(response.read().decode("utf-8"))
    return result.get("data", result) if isinstance(result, dict) else {}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MuJoCo-first VLA execution agent for the three-motor arm.")
    parser.add_argument("--api-base", required=True)
    parser.add_argument("--device-id", default="nanopi-m5")
    parser.add_argument("--robot-id", default="rehab-arm-alpha")
    parser.add_argument("--project-id", default="")
    parser.add_argument("--poll-hz", type=float, default=5.0)
    parser.add_argument("--max-candidate-age-s", type=float, default=2.0)
    parser.add_argument("--shadow-timeout-s", type=float, default=8.0)
    parser.add_argument("--shadow-tolerance-rad", type=float, default=0.04)
    parser.add_argument("--enable-hardware-tx", action="store_true")
    parser.add_argument("--confirm-onsite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.enable_hardware_tx and not args.confirm_onsite:
        raise SystemExit("--enable-hardware-tx requires --confirm-onsite")
    if args.poll_hz <= 0.0:
        raise SystemExit("--poll-hz must be positive")

    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import JointState
    from std_msgs.msg import String
    from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

    class ExecutionNode(Node):
        def __init__(self) -> None:
            super().__init__("rehab_arm_vla_mujoco_execution_agent")
            self.sim_pub = self.create_publisher(JointTrajectory, SIM_TOPIC, 10)
            self.hardware_pub = self.create_publisher(JointTrajectory, HARDWARE_TOPIC, 10)
            self.sim_positions: dict[str, float] = {}
            self.motion_allowed = False
            self.last_safety_rx_monotonic = 0.0
            self.create_subscription(JointState, SIM_STATE_TOPIC, self._on_sim_state, 20)
            self.create_subscription(String, SAFETY_TOPIC, self._on_safety, 20)

        def _on_sim_state(self, msg: JointState) -> None:
            self.sim_positions = {name: float(msg.position[index]) for index, name in enumerate(msg.name) if index < len(msg.position)}

        def _on_safety(self, msg: String) -> None:
            try:
                payload = json.loads(msg.data)
            except Exception:
                self.motion_allowed = False
                return
            self.motion_allowed = payload.get("motion_allowed") is True and payload.get("emergency_stop") is not True
            self.last_safety_rx_monotonic = time.monotonic()

        def publish(self, topic: str, names: list[str], positions: list[float], duration_s: float) -> None:
            message = JointTrajectory()
            message.header.stamp = self.get_clock().now().to_msg()
            message.joint_names = names
            point = JointTrajectoryPoint()
            point.positions = positions
            point.time_from_start.sec = int(duration_s)
            point.time_from_start.nanosec = int((duration_s - int(duration_s)) * 1e9)
            message.points = [point]
            (self.sim_pub if topic == SIM_TOPIC else self.hardware_pub).publish(message)

    rclpy.init()
    node = ExecutionNode()
    latest_url = f"{args.api_base.rstrip('/')}/api/rehab-arm/v1/devices/{args.device_id}/ik-candidate/latest"
    readiness_url = f"{args.api_base.rstrip('/')}/api/rehab-arm/v1/devices/{args.device_id}/simulation-readiness"
    processed: set[str] = set()
    retry_after: dict[str, float] = {}
    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.0)
            try:
                candidate = _request_json(latest_url)
                staged = validate_candidate(candidate, now=time.time(), max_age_s=args.max_candidate_age_s)
                candidate_id = staged["candidate_id"]
                if not candidate_id or candidate_id in processed or time.monotonic() < retry_after.get(candidate_id, 0.0):
                    time.sleep(1.0 / args.poll_hz)
                    continue
                node.publish(SIM_TOPIC, staged["visual_joint_names"], staged["visual_target"], staged["duration_s"])
                deadline = time.time() + args.shadow_timeout_s
                shadow_passed = False
                while time.time() < deadline and rclpy.ok():
                    rclpy.spin_once(node, timeout_sec=0.05)
                    errors = [
                        abs(node.sim_positions.get(name, float("inf")) - target)
                        for name, target in zip(staged["visual_joint_names"], staged["visual_target"])
                    ]
                    if errors and max(errors) <= args.shadow_tolerance_rad:
                        shadow_passed = True
                        break
                _request_json(
                    readiness_url,
                    payload={
                        "robot_id": args.robot_id,
                        "device_id": args.device_id,
                        "project_id": args.project_id,
                        "report": {
                            "ok": shadow_passed,
                            "candidate_id": candidate_id,
                            "readiness": "mujoco_target_reached" if shadow_passed else "mujoco_target_timeout",
                            "control_boundary": "simulation_readiness_only_not_motion_permission",
                        },
                    },
                )
                if not shadow_passed:
                    retry_after[candidate_id] = time.monotonic() + 1.0
                    continue
                processed.add(candidate_id)
                if args.enable_hardware_tx and args.confirm_onsite:
                    if staged["ik_status"] != "candidate_ready":
                        node.get_logger().warn("approximate IK is not eligible for hardware publication")
                    elif not node.motion_allowed or time.monotonic() - node.last_safety_rx_monotonic > 1.0:
                        node.get_logger().warn("M33 motion_allowed is not fresh/true; hardware publication blocked")
                    else:
                        node.publish(HARDWARE_TOPIC, staged["hardware_joint_names"], staged["hardware_target"], staged["duration_s"])
                        node.get_logger().info(f"published confirmed hardware candidate {candidate_id}")
            except Exception as exc:
                node.get_logger().debug(f"candidate waiting: {exc}")
            time.sleep(1.0 / args.poll_hz)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
