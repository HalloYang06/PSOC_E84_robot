#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import time
from typing import Sequence


MODEL_PATH = '/home/cal/medical_arm_mujoco/medical_arm_mujoco.xml'
TOPIC = '/arm_controller/joint_trajectory'
VISUAL_ZERO = [-0.236, -0.675, 0.0, -1.12, -1.57, 1.05]
VISUAL_CTRL_SCALES = [1.0, -1.0, 1.0, 1.0, 1.0, 1.0]
JOINT_NAMES = [
    'jian_hengxiang_joint',
    'jian_zongxiang_joint',
    'jian_xuanzhuan_joint',
    'zhou_zongxiang_joint',
    'wanbu_zongxiang_joint',
    'wanbu_hengxiang_joint',
]
HARDWARE_JOINT_NAMES = [
    'elbow_lift_joint',
    'shoulder_abduction_joint',
    'upper_arm_rotation_joint',
]
HARDWARE_LIMITS = {
    'elbow_lift_joint': (0.0, 1.8),
    'shoulder_abduction_joint': (0.0, math.radians(150.0)),
    'upper_arm_rotation_joint': (-1.2, 1.2),
}
# MuJoCo control sliders are hardware-frame commands for the mounted motors.
HARDWARE_CTRL_INDICES = (1, 3, 2)


def rpm_to_velocity_rad_s(rpm: int | float) -> float:
    return abs(float(rpm)) * 2.0 * math.pi / 60.0


def visual_positions_from_controls(controls: Sequence[float]) -> list[float]:
    return [
        float(offset) + float(scale) * float(control)
        for offset, scale, control in zip(VISUAL_ZERO, VISUAL_CTRL_SCALES, controls)
    ]


def hardware_positions_from_controls(controls: Sequence[float]) -> list[float]:
    return [float(controls[index]) for index in HARDWARE_CTRL_INDICES]


def hardware_limit_issues(hardware_positions: Sequence[float]) -> list[str]:
    issues: list[str] = []
    for name, position in zip(HARDWARE_JOINT_NAMES, hardware_positions):
        low, high = HARDWARE_LIMITS[name]
        value = float(position)
        if value < low or value > high:
            issues.append(f'{name}={value:.4f} rad outside [{low:.4f}, {high:.4f}]')
    return issues


def has_changed(left: Sequence[float], right: Sequence[float], deadband: float) -> bool:
    return any(abs(float(a) - float(b)) > deadband for a, b in zip(left, right))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Open the tuned visual-zero MuJoCo viewer and optionally publish its sliders to hardware.',
    )
    parser.add_argument('--model-path', default=MODEL_PATH)
    parser.add_argument('--topic', default=TOPIC)
    parser.add_argument('--enable-hardware-tx', action='store_true')
    parser.add_argument('--confirm-onsite', action='store_true')
    parser.add_argument('--publish-initial', action='store_true')
    parser.add_argument('--publish-rate-hz', type=float, default=5.0)
    parser.add_argument('--deadband-rad', type=float, default=0.005)
    parser.add_argument('--rpm', type=int, default=3)
    parser.add_argument('--current-ma', type=int, default=3000)
    parser.add_argument('--duration', type=float, default=0.4)
    return parser


def make_trajectory_message(hardware_positions: Sequence[float], args: argparse.Namespace):
    from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

    msg = JointTrajectory()
    point = JointTrajectoryPoint()
    msg.joint_names = list(HARDWARE_JOINT_NAMES)
    point.positions = [float(value) for value in hardware_positions]
    point.velocities = [rpm_to_velocity_rad_s(args.rpm)] * len(HARDWARE_JOINT_NAMES)
    point.effort = [float(args.current_ma) / 1000.0] * len(HARDWARE_JOINT_NAMES)
    duration = max(float(args.duration), 0.02)
    point.time_from_start.sec = int(duration)
    point.time_from_start.nanosec = int((duration - int(duration)) * 1e9)
    msg.points = [point]
    return msg


def configure_hardware_slider_ranges(model) -> None:
    ranges = {
        1: HARDWARE_LIMITS['elbow_lift_joint'],
        3: HARDWARE_LIMITS['shoulder_abduction_joint'],
        2: HARDWARE_LIMITS['upper_arm_rotation_joint'],
    }
    for index, (low, high) in ranges.items():
        if index < len(model.actuator_ctrlrange):
            model.actuator_ctrlrange[index][0] = float(low)
            model.actuator_ctrlrange[index][1] = float(high)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.enable_hardware_tx and not args.confirm_onsite:
        raise SystemExit('--enable-hardware-tx requires --confirm-onsite')
    if args.publish_rate_hz <= 0.0:
        raise SystemExit('--publish-rate-hz must be positive')
    if args.deadband_rad < 0.0:
        raise SystemExit('--deadband-rad must be non-negative')

    import mujoco
    import mujoco.viewer

    model = mujoco.MjModel.from_xml_path(args.model_path)
    data = mujoco.MjData(model)
    configure_hardware_slider_ranges(model)

    qpos_addr = []
    for name in JOINT_NAMES:
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        if joint_id < 0:
            raise RuntimeError(f'missing joint: {name}')
        qpos_addr.append(int(model.jnt_qposadr[joint_id]))

    if model.nu < len(VISUAL_ZERO):
        raise RuntimeError(f'expected at least {len(VISUAL_ZERO)} controls, got {model.nu}')
    data.ctrl[:len(VISUAL_ZERO)] = [0.0] * len(VISUAL_ZERO)
    for addr, value in zip(qpos_addr, visual_positions_from_controls(data.ctrl[:len(VISUAL_ZERO)])):
        data.qpos[addr] = value
    mujoco.mj_forward(model, data)

    ros_node = None
    publisher = None
    if args.enable_hardware_tx:
        import rclpy

        rclpy.init()
        ros_node = rclpy.create_node('medical_arm_visual_zero_hardware_control')
        from trajectory_msgs.msg import JointTrajectory

        publisher = ros_node.create_publisher(JointTrajectory, args.topic, 10)
        print(f'HARDWARE TX ENABLED topic={args.topic}', flush=True)
        print(
            'slider mapping: motor4/elbow_lift=ctrl[1], '
            'motor5/shoulder_abduction=ctrl[3], motor6/upper_arm_rotation=ctrl[2]',
            flush=True,
        )
    else:
        print('hardware TX disabled; viewer display only', flush=True)

    print('visual-zero actual qpos=', [round(value, 6) for value in visual_positions_from_controls(data.ctrl)], flush=True)
    print('hardware command at visual zero=', hardware_positions_from_controls(data.ctrl), flush=True)
    print('close the MuJoCo viewer window to exit', flush=True)

    last_publish_time = 0.0
    last_published = hardware_positions_from_controls(data.ctrl)
    publish_initial_pending = bool(args.publish_initial)
    last_issue_text = ''
    min_publish_period = 1.0 / float(args.publish_rate_hz)

    try:
        with mujoco.viewer.launch_passive(model, data) as viewer:
            while viewer.is_running():
                controls = [float(value) for value in data.ctrl[:len(VISUAL_ZERO)]]
                for addr, value in zip(qpos_addr, visual_positions_from_controls(controls)):
                    data.qpos[addr] = value
                mujoco.mj_forward(model, data)
                viewer.sync()

                if ros_node is not None and publisher is not None:
                    import rclpy

                    rclpy.spin_once(ros_node, timeout_sec=0.0)
                    hardware_positions = hardware_positions_from_controls(controls)
                    issues = hardware_limit_issues(hardware_positions)
                    if issues:
                        issue_text = '; '.join(issues)
                        if issue_text != last_issue_text:
                            print(f'not publishing: {issue_text}', flush=True)
                            last_issue_text = issue_text
                    else:
                        last_issue_text = ''
                        now = time.time()
                        changed = has_changed(hardware_positions, last_published, float(args.deadband_rad))
                        if (publish_initial_pending or changed) and now - last_publish_time >= min_publish_period:
                            msg = make_trajectory_message(hardware_positions, args)
                            msg.header.stamp = ros_node.get_clock().now().to_msg()
                            publisher.publish(msg)
                            last_publish_time = now
                            last_published = list(hardware_positions)
                            publish_initial_pending = False
                            print(
                                'published hardware positions rad='
                                + ','.join(f'{value:.4f}' for value in hardware_positions),
                                flush=True,
                            )

                time.sleep(1.0 / 60.0)
    finally:
        if ros_node is not None:
            import rclpy

            ros_node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
