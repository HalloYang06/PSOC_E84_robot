#!/usr/bin/env python3
from __future__ import annotations

import json
from types import SimpleNamespace

try:
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import JointState
    from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
except ModuleNotFoundError:  # Allows unit tests without a sourced ROS environment.
    rclpy = None  # type: ignore[assignment]
    Node = object  # type: ignore[assignment,misc]

    class JointState:  # type: ignore[no-redef]
        def __init__(self) -> None:
            self.header = SimpleNamespace(stamp=SimpleNamespace(sec=0, nanosec=0))
            self.name: list[str] = []
            self.position: list[float] = []

    class JointTrajectoryPoint:  # type: ignore[no-redef]
        def __init__(self) -> None:
            self.positions: list[float] = []
            self.time_from_start = SimpleNamespace(sec=0, nanosec=0)

    class JointTrajectory:  # type: ignore[no-redef]
        def __init__(self) -> None:
            self.header = SimpleNamespace(stamp=SimpleNamespace(sec=0, nanosec=0))
            self.joint_names: list[str] = []
            self.points: list[JointTrajectoryPoint] = []


DEFAULT_JOINT_MAP = {
    # Temporary bench rule: external motor7 publishes legacy forearm_rotation_joint
    # and shadows the medical-arm shoulder/upper-arm rotation joint.
    'forearm_rotation_joint': 'jian_xuanzhuan_joint',
}

DEFAULT_TARGET_JOINT_NAMES = [
    'jian_hengxiang_joint',
    'jian_zongxiang_joint',
    'jian_xuanzhuan_joint',
    'zhou_zongxiang_joint',
    'wanbu_zongxiang_joint',
    'wanbu_hengxiang_joint',
]

DEFAULT_PLACEHOLDER_POSITIONS = {
    name: 0.0 for name in DEFAULT_TARGET_JOINT_NAMES
}


def parse_joint_map(text: str | None) -> dict[str, str]:
    if not text:
        return dict(DEFAULT_JOINT_MAP)
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError('joint_map_json must be a JSON object')
    result: dict[str, str] = {}
    for source, target in payload.items():
        if not isinstance(source, str) or not isinstance(target, str):
            raise ValueError('joint_map_json keys and values must be strings')
        result[source] = target
    if not result:
        raise ValueError('joint_map_json must contain at least one mapping')
    return result


def parse_string_list(text: str | None, *, default: list[str], parameter_name: str) -> list[str]:
    if not text:
        return list(default)
    payload = json.loads(text)
    if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
        raise ValueError(f'{parameter_name} must be a JSON string list')
    if not payload:
        raise ValueError(f'{parameter_name} must contain at least one joint')
    return list(payload)


def parse_placeholder_positions(text: str | None) -> dict[str, float]:
    if not text:
        return dict(DEFAULT_PLACEHOLDER_POSITIONS)
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError('placeholder_positions_json must be a JSON object')
    result: dict[str, float] = {}
    for joint_name, position in payload.items():
        if not isinstance(joint_name, str) or not isinstance(position, (int, float)):
            raise ValueError('placeholder_positions_json keys must be strings and values must be numbers')
        result[joint_name] = float(position)
    return result


def build_shadow_trajectory(
    source_msg: JointState,
    joint_map: dict[str, str],
    duration_sec: float,
    *,
    publish_full_target: bool = False,
    target_joint_names: list[str] | None = None,
    placeholder_positions: dict[str, float] | None = None,
) -> JointTrajectory | None:
    mapped_positions: dict[str, float] = {}
    for index, source_name in enumerate(source_msg.name):
        if source_name not in joint_map or index >= len(source_msg.position):
            continue
        mapped_positions[joint_map[source_name]] = float(source_msg.position[index])
    if not mapped_positions and not publish_full_target:
        return None

    if publish_full_target:
        joints = list(target_joint_names or DEFAULT_TARGET_JOINT_NAMES)
        placeholders = placeholder_positions or DEFAULT_PLACEHOLDER_POSITIONS
        targets = [(name, mapped_positions.get(name, float(placeholders.get(name, 0.0)))) for name in joints]
    else:
        targets = list(mapped_positions.items())

    msg = JointTrajectory()
    msg.header.stamp = source_msg.header.stamp
    msg.joint_names = [name for name, _ in targets]
    point = JointTrajectoryPoint()
    point.positions = [position for _, position in targets]
    whole_sec = int(max(duration_sec, 0.02))
    point.time_from_start.sec = whole_sec
    point.time_from_start.nanosec = int((max(duration_sec, 0.02) - whole_sec) * 1e9)
    msg.points = [point]
    return msg


class MedicalArmShadowRelayNode(Node):
    def __init__(self) -> None:
        super().__init__('medical_arm_shadow_relay')
        self.declare_parameter('source_joint_state_topic', '/joint_states')
        self.declare_parameter('target_trajectory_topic', '/sim/medical_arm/joint_trajectory')
        self.declare_parameter('joint_map_json', json.dumps(DEFAULT_JOINT_MAP, separators=(',', ':')))
        self.declare_parameter('publish_full_target', True)
        self.declare_parameter('target_joint_names_json', json.dumps(DEFAULT_TARGET_JOINT_NAMES, separators=(',', ':')))
        self.declare_parameter('placeholder_positions_json', json.dumps(DEFAULT_PLACEHOLDER_POSITIONS, separators=(',', ':')))
        self.declare_parameter('duration_sec', 0.25)

        self.source_topic = str(self.get_parameter('source_joint_state_topic').value)
        self.target_topic = str(self.get_parameter('target_trajectory_topic').value)
        self.joint_map = parse_joint_map(str(self.get_parameter('joint_map_json').value))
        self.publish_full_target = bool(self.get_parameter('publish_full_target').value)
        self.target_joint_names = parse_string_list(
            str(self.get_parameter('target_joint_names_json').value),
            default=DEFAULT_TARGET_JOINT_NAMES,
            parameter_name='target_joint_names_json',
        )
        self.placeholder_positions = parse_placeholder_positions(
            str(self.get_parameter('placeholder_positions_json').value)
        )
        self.duration_sec = float(self.get_parameter('duration_sec').value)

        self.publisher = self.create_publisher(JointTrajectory, self.target_topic, 10)
        self.subscription = self.create_subscription(JointState, self.source_topic, self.on_joint_state, 20)
        self.get_logger().info(
            f'Medical arm shadow relay ready: {self.source_topic} -> {self.target_topic}, '
            f'joint_map={self.joint_map}, publish_full_target={self.publish_full_target}, '
            f'target_joint_names={self.target_joint_names}'
        )

    def on_joint_state(self, msg: JointState) -> None:
        trajectory = build_shadow_trajectory(
            msg,
            self.joint_map,
            self.duration_sec,
            publish_full_target=self.publish_full_target,
            target_joint_names=self.target_joint_names,
            placeholder_positions=self.placeholder_positions,
        )
        if trajectory is None:
            return
        self.publisher.publish(trajectory)


def main(args=None) -> None:
    if rclpy is None:
        raise RuntimeError('rclpy is required to run medical_arm_shadow_relay_node')
    rclpy.init(args=args)
    node = MedicalArmShadowRelayNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
