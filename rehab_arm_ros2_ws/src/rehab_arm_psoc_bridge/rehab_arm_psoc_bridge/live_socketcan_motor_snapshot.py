#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import select
import socket
import struct
import sys
import time
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.candump_motor_telemetry import (
        CONTROL_BOUNDARY,
        decode_cansimple_encoder_estimate,
        decode_cansimple_heartbeat,
        decode_private_active_report,
    )
    from rehab_arm_psoc_bridge.data_recording import (
        JSONL_SCHEMA_VERSION,
        RECORDER_VERSION,
        make_motor_state_payload,
        make_payload_record,
        sanitize_identifier,
        write_jsonl_record,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.candump_motor_telemetry import (
        CONTROL_BOUNDARY,
        decode_cansimple_encoder_estimate,
        decode_cansimple_heartbeat,
        decode_private_active_report,
    )
    from rehab_arm_psoc_bridge.data_recording import (
        JSONL_SCHEMA_VERSION,
        RECORDER_VERSION,
        make_motor_state_payload,
        make_payload_record,
        sanitize_identifier,
        write_jsonl_record,
    )


CAN_EFF_FLAG = 0x80000000
CAN_EFF_MASK = 0x1FFFFFFF
CAN_SFF_MASK = 0x7FF
CAN_FRAME_STRUCT = struct.Struct('=IB3x8s')

PRIVATE_MASTER_ID = 0xFD
PRIVATE_ACTIVE_REPORT_TYPE = 0x18


def pack_socketcan_frame(can_id: int, data: bytes, is_extended: bool = False) -> bytes:
    if len(data) > 8:
        raise ValueError('classic CAN payload must be at most 8 bytes')
    socket_id = can_id | (CAN_EFF_FLAG if is_extended else 0)
    return CAN_FRAME_STRUCT.pack(socket_id, len(data), data.ljust(8, b'\x00'))


def unpack_socketcan_frame(raw: bytes) -> dict[str, object]:
    socket_id, dlc, padded = CAN_FRAME_STRUCT.unpack(raw)
    is_extended = bool(socket_id & CAN_EFF_FLAG)
    can_id = socket_id & (CAN_EFF_MASK if is_extended else CAN_SFF_MASK)
    return {
        'can_id': can_id,
        'is_extended': is_extended,
        'dlc': dlc,
        'data': padded[:dlc],
    }


def private_ext_id(command_type: int, data2: int, motor_id: int) -> int:
    return ((command_type & 0x1F) << 24) | ((data2 & 0xFFFF) << 8) | (motor_id & 0xFF)


def private_active_report_frame(motor_id: int, enabled: bool) -> bytes:
    payload = bytes([1, 2, 3, 4, 5, 6, 1 if enabled else 0, 0])
    return pack_socketcan_frame(
        private_ext_id(PRIVATE_ACTIVE_REPORT_TYPE, PRIVATE_MASTER_ID, motor_id),
        payload,
        is_extended=True,
    )


def frame_key(frame: dict[str, object]) -> str:
    can_id = int(frame['can_id'])
    return f'0x{can_id:08X}' if frame.get('is_extended') else f'0x{can_id:03X}'


def decode_live_motor_frame(
    frame: dict[str, object],
    heartbeat_by_node: dict[int, dict[str, object]],
) -> tuple[str | None, dict[str, object] | None]:
    can_id = int(frame['can_id'])
    data = frame['data']
    if not isinstance(data, bytes):
        return None, None

    if frame.get('is_extended'):
        motor = decode_private_active_report({
            'can_id': can_id,
            'data': data,
            'relative_time_s': 0.0,
        })
        if motor:
            motor['control_boundary'] = CONTROL_BOUNDARY
            return f'motor{motor["motor_id"]}_active_report', motor
        return None, None

    cmd_id = can_id & 0x1F
    node_id = can_id >> 5
    raw_frame = {
        'can_id': can_id,
        'data': data,
        'relative_time_s': 0.0,
    }
    if cmd_id == 0x001:
        heartbeat = decode_cansimple_heartbeat(raw_frame)
        if heartbeat:
            heartbeat['control_boundary'] = CONTROL_BOUNDARY
            heartbeat_by_node[node_id] = heartbeat
            return f'motor{node_id}_heartbeat', heartbeat
        return None, None
    if cmd_id == 0x009:
        motor = decode_cansimple_encoder_estimate(raw_frame, heartbeat_by_node.get(node_id))
        if motor:
            motor['control_boundary'] = CONTROL_BOUNDARY
            return f'motor{motor["motor_id"]}_encoder', motor
    return None, None


def collect_live_snapshot(
    iface: str,
    duration_s: float,
    active_report_motor_ids: list[int] | None = None,
) -> dict[str, object]:
    active_ids = active_report_motor_ids or []
    counts: dict[str, int] = {}
    latest: dict[str, dict[str, object]] = {}
    heartbeat_by_node: dict[int, dict[str, object]] = {}

    sock = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    sock.bind((iface,))
    try:
        for motor_id in active_ids:
            sock.send(private_active_report_frame(motor_id, True))

        end = time.monotonic() + duration_s
        while time.monotonic() < end:
            readable, _, _ = select.select([sock], [], [], min(0.2, max(0.0, end - time.monotonic())))
            if not readable:
                continue
            frame = unpack_socketcan_frame(sock.recv(CAN_FRAME_STRUCT.size))
            key = frame_key(frame)
            counts[key] = counts.get(key, 0) + 1
            decoded_key, decoded = decode_live_motor_frame(frame, heartbeat_by_node)
            if decoded_key and decoded:
                latest[decoded_key] = decoded
    finally:
        for motor_id in active_ids:
            try:
                sock.send(private_active_report_frame(motor_id, False))
            except OSError:
                pass
        sock.close()

    return {
        'schema_version': 'live_socketcan_motor_snapshot_v1',
        'iface': iface,
        'duration_s': duration_s,
        'active_report_motor_ids': active_ids,
        'counts': counts,
        'latest': latest,
        'motor_state_compatible_entries': [
            value for key, value in sorted(latest.items())
            if key.endswith('_encoder') or key.endswith('_active_report')
        ],
        'control_boundary': CONTROL_BOUNDARY,
        'safety_note': 'telemetry only; active-report requests do not send position, velocity, torque, 0x320, or motion commands',
    }


def make_snapshot_session_metadata(
    session_id: str,
    device_id: str,
    robot_id: str,
    now: float | None = None,
) -> dict[str, object]:
    return {
        'record_type': 'session_metadata',
        'schema_version': JSONL_SCHEMA_VERSION,
        'ts_unix': time.time() if now is None else now,
        'session_id': sanitize_identifier(session_id),
        'device_id': device_id,
        'robot_id': robot_id,
        'software_version': 'dev',
        'recorder_version': RECORDER_VERSION,
        'mode': 'live_socketcan_motor_snapshot',
        'source': 'live_socketcan_motor_snapshot',
        'sync_status': 'local_only',
        'topics': ['/rehab_arm/motor_state'],
        'optional_topics': [],
        'motion_allowed_expected': False,
        'control_boundary': CONTROL_BOUNDARY,
    }


def build_snapshot_jsonl_records(
    snapshot: dict[str, object],
    robot_id: str,
    device_id: str,
    session_id: str,
    now: float | None = None,
) -> list[dict[str, object]]:
    ts = time.time() if now is None else now
    sid = sanitize_identifier(session_id)
    entries = snapshot.get('motor_state_compatible_entries', [])
    motors = [dict(item) for item in entries if isinstance(item, dict)]
    payload = make_motor_state_payload(
        motors,
        robot_id=robot_id,
        device_id=device_id,
        now=ts,
        source='live_socketcan_motor_snapshot',
    )
    payload['session_id'] = sid
    payload['motor_count'] = len(motors)
    payload['frame_counts'] = dict(snapshot.get('counts', {})) if isinstance(snapshot.get('counts'), dict) else {}
    payload['snapshot_schema_version'] = snapshot.get('schema_version', 'live_socketcan_motor_snapshot_v1')
    return [
        make_snapshot_session_metadata(sid, device_id, robot_id, now=ts),
        make_payload_record('/rehab_arm/motor_state', payload, now=ts),
    ]


def write_snapshot_jsonl(
    output_path: str | Path,
    snapshot: dict[str, object],
    robot_id: str,
    device_id: str,
    session_id: str,
    now: float | None = None,
) -> Path:
    path = Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    records = build_snapshot_jsonl_records(snapshot, robot_id, device_id, session_id, now=now)
    with path.open('w', encoding='utf-8') as handle:
        for record in records:
            write_jsonl_record(handle, record)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Capture a short live SocketCAN motor telemetry snapshot.')
    parser.add_argument('--iface', default='can0', help='SocketCAN interface, default can0')
    parser.add_argument('--duration', type=float, default=3.0, help='Capture duration in seconds')
    parser.add_argument(
        '--enable-active-report',
        type=int,
        action='append',
        default=[],
        metavar='MOTOR_ID',
        help='Temporarily enable private active-report for this motor id, then disable it on exit.',
    )
    parser.add_argument('--pretty', action='store_true', help='Pretty-print JSON')
    parser.add_argument('--output-jsonl', help='Optional recorder-compatible JSONL output path')
    parser.add_argument('--device-id', default='nanopi-m5', help='Device id for JSONL output')
    parser.add_argument('--robot-id', default='rehab-arm-alpha', help='Robot id for JSONL output')
    parser.add_argument('--session-id', help='Session id for JSONL output. Defaults to live_socketcan_<unix time>.')
    args = parser.parse_args(argv)

    if args.duration <= 0:
        parser.error('--duration must be positive')

    snapshot = collect_live_snapshot(args.iface, args.duration, args.enable_active_report)
    if args.output_jsonl:
        session_id = args.session_id or f'live_socketcan_{int(time.time())}'
        output_path = write_snapshot_jsonl(
            args.output_jsonl,
            snapshot,
            robot_id=args.robot_id,
            device_id=args.device_id,
            session_id=session_id,
        )
        snapshot['output_jsonl'] = str(output_path)
        snapshot['session_id'] = sanitize_identifier(session_id)
    print(json.dumps(snapshot, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=args.pretty))
    return 0 if snapshot['counts'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
