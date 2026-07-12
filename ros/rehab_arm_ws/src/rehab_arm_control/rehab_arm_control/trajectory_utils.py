from __future__ import annotations

from builtin_interfaces.msg import Duration
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint


JOINT_NAMES = [
    'shoulder_lift_joint',
    'elbow_lift_joint',
    'shoulder_abduction_joint',
    'upper_arm_rotation_joint',
    'forearm_rotation_joint',
]


def duration(seconds: float) -> Duration:
    msg = Duration()
    msg.sec = int(seconds)
    msg.nanosec = int((seconds - msg.sec) * 1_000_000_000)
    return msg


def point(positions: list[float], seconds: float) -> JointTrajectoryPoint:
    msg = JointTrajectoryPoint()
    msg.positions = positions
    msg.velocities = [0.0] * len(positions)
    msg.time_from_start = duration(seconds)
    return msg


def multijoint_demo_trajectory() -> JointTrajectory:
    msg = JointTrajectory()
    msg.joint_names = JOINT_NAMES
    msg.points = [
        point([0.00, 0.20, 0.00, 0.00, 0.00], 0.5),
        point([0.35, 0.70, 0.18, 0.25, -0.20], 3.0),
        point([0.55, 1.05, -0.10, -0.35, 0.35], 6.0),
        point([0.20, 0.45, 0.05, 0.10, 0.00], 9.0),
        point([0.00, 0.20, 0.00, 0.00, 0.00], 12.0),
    ]
    return msg
