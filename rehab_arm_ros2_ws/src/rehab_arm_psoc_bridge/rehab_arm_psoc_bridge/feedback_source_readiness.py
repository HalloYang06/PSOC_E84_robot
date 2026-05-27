#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.candump_motor_telemetry import (
        CANSIMPLE_ENCODER_ESTIMATE_CMD,
        CANSIMPLE_HEARTBEAT_CMD,
        PRIVATE_ACTIVE_REPORT_TYPE,
        PRIVATE_MASTER_ID,
        cansimple_cmd_id,
        cansimple_node_id,
        parse_candump_line,
    )
    from rehab_arm_psoc_bridge.check_m33_motor_status_presence import (
        PSOC_STATUS_ID,
        PSOC_TARGET_ID,
        build_presence_report,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.candump_motor_telemetry import (  # type: ignore[no-redef]
        CANSIMPLE_ENCODER_ESTIMATE_CMD,
        CANSIMPLE_HEARTBEAT_CMD,
        PRIVATE_ACTIVE_REPORT_TYPE,
        PRIVATE_MASTER_ID,
        cansimple_cmd_id,
        cansimple_node_id,
        parse_candump_line,
    )
    from rehab_arm_psoc_bridge.check_m33_motor_status_presence import (  # type: ignore[no-redef]
        PSOC_STATUS_ID,
        PSOC_TARGET_ID,
        build_presence_report,
    )


EXPECTED_CANSIMPLE_NODES = [3]
EXPECTED_LINGZU_MOTOR_IDS = [4, 5, 6, 7]
CONTROL_BOUNDARY = 'readonly_feedback_source_check_not_motion_permission'


def _lingzu_active_report_motor_id(can_id: int) -> int | None:
    if can_id <= 0x7FF:
        return None
    if (can_id & 0xFF) != PRIVATE_MASTER_ID:
        return None
    if ((can_id >> 24) & 0x1F) != PRIVATE_ACTIVE_REPORT_TYPE:
        return None
    return (can_id >> 8) & 0xFF


def build_feedback_source_readiness_report(path: str | Path) -> dict[str, object]:
    source = Path(path).expanduser()
    m33_report = build_presence_report(source)
    frame_count = 0
    parse_error_count = 0
    target_count = 0
    psoc_status_count = 0
    cansimple_heartbeats: dict[int, int] = {}
    cansimple_encoder_estimates: dict[int, int] = {}
    lingzu_active_reports: dict[int, int] = {}
    other_raw_ids: dict[str, int] = {}

    for line in source.read_text(encoding='utf-8', errors='replace').splitlines():
        if not line.strip():
            continue
        frame = parse_candump_line(line)
        if frame is None:
            parse_error_count += 1
            continue
        frame_count += 1
        can_id = int(frame['can_id'])
        data = frame['data']
        if can_id == PSOC_TARGET_ID:
            target_count += 1
        if can_id == PSOC_STATUS_ID:
            psoc_status_count += 1
        if 0x330 <= can_id <= 0x337:
            continue

        cmd_id = cansimple_cmd_id(can_id) if can_id <= 0x7FF else None
        node_id = cansimple_node_id(can_id) if can_id <= 0x7FF else None
        if cmd_id == CANSIMPLE_HEARTBEAT_CMD and node_id is not None:
            cansimple_heartbeats[node_id] = cansimple_heartbeats.get(node_id, 0) + 1
            continue
        if cmd_id == CANSIMPLE_ENCODER_ESTIMATE_CMD and node_id is not None:
            cansimple_encoder_estimates[node_id] = cansimple_encoder_estimates.get(node_id, 0) + 1
            continue

        lingzu_motor_id = _lingzu_active_report_motor_id(can_id)
        if isinstance(data, bytes) and len(data) == 8 and lingzu_motor_id is not None:
            lingzu_active_reports[lingzu_motor_id] = lingzu_active_reports.get(lingzu_motor_id, 0) + 1
            continue

        can_id_hex = f'0x{can_id:03X}' if can_id <= 0x7FF else f'0x{can_id:X}'
        other_raw_ids[can_id_hex] = other_raw_ids.get(can_id_hex, 0) + 1

    missing_cansimple_nodes = [
        node_id for node_id in EXPECTED_CANSIMPLE_NODES
        if cansimple_encoder_estimates.get(node_id, 0) == 0 and cansimple_heartbeats.get(node_id, 0) == 0
    ]
    missing_lingzu_motors = [
        motor_id for motor_id in EXPECTED_LINGZU_MOTOR_IDS
        if lingzu_active_reports.get(motor_id, 0) == 0
    ]
    raw_motor_feedback_count = (
        sum(cansimple_heartbeats.values())
        + sum(cansimple_encoder_estimates.values())
        + sum(lingzu_active_reports.values())
    )
    fresh_m33_count = int(m33_report.get('fresh_m33_motor_status_count') or 0)
    stale_m33_count = int(m33_report.get('stale_m33_motor_status_count') or 0)
    valid_m33_count = int(m33_report.get('valid_m33_motor_status_count') or 0)

    errors: list[str] = []
    warnings: list[str] = []
    if frame_count == 0:
        errors.append('candump contains no parseable CAN frames')
    if target_count:
        errors.append('0x320 target frames were observed; this was not a readonly capture')
    if valid_m33_count == 0:
        warnings.append('no valid M33 0x330~0x334 motor status frames observed')
    elif fresh_m33_count == 0:
        warnings.append('M33 motor status frames are present but all are stale')
    if raw_motor_feedback_count == 0:
        warnings.append('no raw motor feedback frames observed from Sitaiwei or Lingzu motors')
    if psoc_status_count == 0:
        warnings.append('0x322 M33 safety/status frames were not observed')

    raw_feedback_ready = raw_motor_feedback_count > 0
    m33_joint_state_ready = fresh_m33_count > 0
    return {
        'schema_version': 'rehab_arm_feedback_source_readiness_v1',
        'ok': not errors,
        'source': str(source),
        'frame_count': frame_count,
        'parse_error_count': parse_error_count + int(m33_report.get('parse_error_count') or 0),
        'raw_motor_feedback_ready': raw_feedback_ready,
        'm33_joint_state_ready': m33_joint_state_ready,
        'safe_to_expect_joint_states': m33_joint_state_ready,
        'decision': (
            'ready_for_ros_joint_states'
            if m33_joint_state_ready
            else 'raw_motor_feedback_present_but_m33_stale'
            if raw_feedback_ready and valid_m33_count > 0
            else 'motor_feedback_source_missing'
        ),
        'm33': {
            'valid_count': valid_m33_count,
            'fresh_count': fresh_m33_count,
            'stale_count': stale_m33_count,
            'ids': m33_report.get('m33_motor_status_ids', {}),
            'motor_ids_by_status_id': m33_report.get('motor_ids_by_status_id', {}),
            'missing_required_ids': m33_report.get('missing_required_m33_motor_status_ids', []),
        },
        'raw_sources': {
            'cansimple_heartbeats_by_node': {
                str(key): value for key, value in sorted(cansimple_heartbeats.items())
            },
            'cansimple_encoder_estimates_by_node': {
                str(key): value for key, value in sorted(cansimple_encoder_estimates.items())
            },
            'lingzu_active_reports_by_motor': {
                str(key): value for key, value in sorted(lingzu_active_reports.items())
            },
            'missing_cansimple_nodes': missing_cansimple_nodes,
            'missing_lingzu_motors': missing_lingzu_motors,
        },
        'safety': {
            'psoc_status_0x322_count': psoc_status_count,
            'target_0x320_count': target_count,
            'motion_command_observed': target_count > 0,
        },
        'other_raw_ids': dict(sorted(other_raw_ids.items())),
        'errors': errors,
        'warnings': warnings,
        'control_boundary': CONTROL_BOUNDARY,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Summarize whether a readonly candump has raw motor feedback and fresh M33 ROS telemetry.',
    )
    parser.add_argument('candump_path')
    parser.add_argument('--pretty', action='store_true')
    parser.add_argument('--output', help='Optional path to write the JSON report.')
    args = parser.parse_args(argv)

    try:
        report = build_feedback_source_readiness_report(args.candump_path)
    except Exception as exc:
        report = {
            'schema_version': 'rehab_arm_feedback_source_readiness_v1',
            'ok': False,
            'errors': [str(exc)],
            'control_boundary': CONTROL_BOUNDARY,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
        return 2

    text = json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=args.pretty)
    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + '\n', encoding='utf-8')
    print(text)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
