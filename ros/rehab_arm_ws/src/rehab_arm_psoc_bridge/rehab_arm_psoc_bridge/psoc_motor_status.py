from __future__ import annotations

import time

from rehab_arm_psoc_bridge.data_recording import make_motor_state_payload


M33_MOTOR_STATUS_BASE_ID = 0x330
M33_MOTOR_STATUS_MAX_ID = 0x337
M33_MOTOR_STATUS_MARKER = 0xB3
M33_MOTOR_STATUS_PROTOCOL_VERSION = 1
UNKNOWN_TEMPERATURE_U8 = 0xFF

MOTOR_STATUS_FLAG_ENABLED = 0x01
MOTOR_STATUS_FLAG_FAULT = 0x02
MOTOR_STATUS_FLAG_LIMITED = 0x04
MOTOR_STATUS_FLAG_EMERGENCY_STOP = 0x08
MOTOR_STATUS_FLAG_STALE = 0x10

JOINT_NAMES_BY_STATUS_SLOT = {
    0: 'shoulder_lift_joint',
    1: 'elbow_lift_joint',
    2: 'shoulder_abduction_joint',
    3: 'upper_arm_rotation_joint',
    4: 'forearm_rotation_joint',
}

MOTOR_VENDOR_BY_ID = {
    3: 'Sitaiwei',
    4: 'Lingzu',
    5: 'Lingzu',
    6: 'Lingzu',
    7: 'Lingzu',
}


def is_m33_motor_status_id(can_id: int) -> bool:
    return M33_MOTOR_STATUS_BASE_ID <= can_id <= M33_MOTOR_STATUS_MAX_ID


def m33_motor_status_slot(can_id: int) -> int:
    return can_id - M33_MOTOR_STATUS_BASE_ID


def _signed_i8(value: int) -> int:
    return value - 256 if value >= 128 else value


def parse_m33_motor_status_frame(can_id: int, data: bytes) -> dict[str, object]:
    payload: dict[str, object] = {
        'protocol': 'm33_motor_status_v1',
        'protocol_status': 'proposed_firmware_pending',
        'raw_can_id': f'0x{can_id:03X}',
        'raw_data': data.hex().upper(),
        'control_boundary': 'telemetry_only_not_motor_command',
    }

    if not is_m33_motor_status_id(can_id):
        payload.update({
            'valid': False,
            'detail': 'not an M33 motor status CAN ID',
        })
        return payload

    slot = m33_motor_status_slot(can_id)
    payload.update({
        'status_slot': slot,
        'joint_name': JOINT_NAMES_BY_STATUS_SLOT.get(slot, f'm33_status_slot_{slot}'),
    })

    if len(data) != 8:
        payload.update({
            'valid': False,
            'detail': 'M33 motor status payload must be 8 bytes',
        })
        return payload

    marker = data[0]
    seq = data[1]
    motor_id = data[2]
    flags = data[3]
    position_mrad = int.from_bytes(data[4:6], 'little', signed=True)
    velocity_drad_s = _signed_i8(data[6])
    temperature_raw = data[7]

    enabled = bool(flags & MOTOR_STATUS_FLAG_ENABLED)
    fault = bool(flags & MOTOR_STATUS_FLAG_FAULT)
    limited = bool(flags & MOTOR_STATUS_FLAG_LIMITED)
    emergency_stop = bool(flags & MOTOR_STATUS_FLAG_EMERGENCY_STOP)
    stale = bool(flags & MOTOR_STATUS_FLAG_STALE)
    temperature_c = None if temperature_raw == UNKNOWN_TEMPERATURE_U8 else float(temperature_raw)

    payload.update({
        'valid': marker == M33_MOTOR_STATUS_MARKER,
        'detail': 'ok' if marker == M33_MOTOR_STATUS_MARKER else 'invalid M33 motor status marker',
        'protocol_version': M33_MOTOR_STATUS_PROTOCOL_VERSION,
        'marker': marker,
        'seq': seq,
        'motor_id': motor_id,
        'vendor': MOTOR_VENDOR_BY_ID.get(motor_id),
        'position': position_mrad / 1000.0,
        'velocity': velocity_drad_s / 10.0,
        'effort': None,
        'current': None,
        'torque': None,
        'temperature': temperature_c,
        'voltage': None,
        'enabled': enabled,
        'fault': fault,
        'limited': limited,
        'emergency_stop': emergency_stop,
        'stale': stale,
        'data_fresh': not stale,
        'status_flags': flags,
        'position_mrad': position_mrad,
        'velocity_drad_s': velocity_drad_s,
        'temperature_raw_u8': temperature_raw,
    })
    return payload


def make_m33_motor_state_payload(
    frames: list[dict[str, object]],
    robot_id: str,
    device_id: str,
    now: float | None = None,
) -> dict[str, object]:
    motors = [dict(frame) for frame in frames if frame.get('valid') is True]
    payload = make_motor_state_payload(
        motors=motors,
        robot_id=robot_id,
        device_id=device_id,
        now=time.time() if now is None else now,
        source='m33_motor_status_v1',
    )
    payload['protocol_status'] = 'proposed_firmware_pending'
    payload['frame_count'] = len(frames)
    payload['valid_motor_count'] = len(motors)
    return payload


def make_joint_state_fields_from_m33_motor_state(
    payload: dict[str, object],
) -> dict[str, list[float] | list[str]]:
    motors = payload.get('motors', [])
    if not isinstance(motors, list):
        return {'name': [], 'position': [], 'velocity': [], 'effort': []}

    names: list[str] = []
    positions: list[float] = []
    velocities: list[float] = []
    efforts: list[float] = []
    for motor in motors:
        if not isinstance(motor, dict):
            continue
        joint_name = motor.get('joint_name')
        position = motor.get('position')
        if motor.get('stale') is True or motor.get('data_fresh') is False:
            continue
        if not isinstance(joint_name, str) or not isinstance(position, (int, float)):
            continue
        velocity = motor.get('velocity')
        effort = motor.get('effort')
        names.append(joint_name)
        positions.append(float(position))
        velocities.append(float(velocity) if isinstance(velocity, (int, float)) else 0.0)
        efforts.append(float(effort) if isinstance(effort, (int, float)) else 0.0)
    return {
        'name': names,
        'position': positions,
        'velocity': velocities,
        'effort': efforts,
    }


def make_current_position_updates_from_m33_motor_state(
    payload: dict[str, object],
    known_joint_names: list[str],
) -> dict[str, float]:
    known = set(known_joint_names)
    fields = make_joint_state_fields_from_m33_motor_state(payload)
    updates: dict[str, float] = {}
    for index, joint_name in enumerate(fields['name']):
        if not isinstance(joint_name, str) or joint_name not in known:
            continue
        positions = fields['position']
        if index < len(positions):
            updates[joint_name] = float(positions[index])
    return updates


class M33MotorStatusAggregator:
    def __init__(self, robot_id: str, device_id: str):
        self.robot_id = robot_id
        self.device_id = device_id
        self.latest_by_slot: dict[int, dict[str, object]] = {}
        self.invalid_frame_count = 0
        self.valid_frame_count = 0

    def accept_frame(
        self,
        can_id: int,
        data: bytes,
        now: float | None = None,
    ) -> dict[str, object] | None:
        motor = parse_m33_motor_status_frame(can_id, data)
        if motor.get('valid') is not True:
            self.invalid_frame_count += 1
            return None

        slot = motor.get('status_slot')
        if isinstance(slot, int):
            self.latest_by_slot[slot] = motor
        self.valid_frame_count += 1
        payload = make_m33_motor_state_payload(
            frames=[self.latest_by_slot[key] for key in sorted(self.latest_by_slot)],
            robot_id=self.robot_id,
            device_id=self.device_id,
            now=now,
        )
        payload['aggregator_valid_frame_count'] = self.valid_frame_count
        payload['aggregator_invalid_frame_count'] = self.invalid_frame_count
        return payload
