from __future__ import annotations

from dataclasses import dataclass

from rehab_arm_psoc_bridge.data_recording import (
    make_joint_state_payload,
    make_payload_record,
)
from rehab_arm_psoc_bridge.psoc_motor_status import (
    M33MotorStatusAggregator,
    make_joint_state_fields_from_m33_motor_state,
)
from rehab_arm_psoc_bridge.psoc_status import parse_psoc_status_payload
from rehab_arm_psoc_bridge.safety_gate import psoc_motion_gate_detail


@dataclass(frozen=True)
class RawCanPayload:
    can_id: int
    data: bytes


def build_m33_ros_topic_records(
    status_data: bytes,
    motor_frames: list[RawCanPayload],
    robot_id: str,
    device_id: str,
    now: float,
) -> dict[str, object]:
    """Build the offline ROS topic contract from M33 CAN telemetry.

    This mirrors the runtime bridge behavior without opening ROS or SocketCAN.
    It is intentionally telemetry-only: motor frames can update joint/motor
    state, but only the parsed 0x322 `motion_allowed` bit can make motion a
    candidate for execution.
    """
    safety_payload = parse_psoc_status_payload(status_data)
    gate_allowed, gate_detail = psoc_motion_gate_detail(safety_payload)

    aggregator = M33MotorStatusAggregator(robot_id, device_id)
    motor_payload = None
    for frame in motor_frames:
        latest = aggregator.accept_frame(frame.can_id, frame.data, now=now)
        if latest is not None:
            motor_payload = latest

    joint_payload = None
    if motor_payload is not None:
        fields = make_joint_state_fields_from_m33_motor_state(motor_payload)
        if fields['name']:
            joint_payload = make_joint_state_payload(
                names=fields['name'],
                positions=fields['position'],
                velocities=fields['velocity'],
                efforts=fields['effort'],
                stamp_sec=int(now),
                stamp_nanosec=int((now - int(now)) * 1_000_000_000),
            )

    topic_records = [
        make_payload_record('/rehab_arm/safety_state', safety_payload, now=now),
    ]
    if motor_payload is not None:
        topic_records.append(make_payload_record('/rehab_arm/motor_state', motor_payload, now=now))
    if joint_payload is not None:
        topic_records.append(make_payload_record('/joint_states', joint_payload, now=now))

    return {
        'schema_version': 'm33_ros_topic_contract_v1',
        'control_boundary': 'm33_safety_status_is_motion_authority',
        'motion_candidate_allowed': gate_allowed,
        'motion_gate_detail': gate_detail,
        'topics': [record['topic'] for record in topic_records],
        'records': topic_records,
        'safety_state': safety_payload,
        'motor_state': motor_payload,
        'joint_state': joint_payload,
    }
