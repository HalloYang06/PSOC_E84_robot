#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.candump_motor_telemetry import parse_candump_line
    from rehab_arm_psoc_bridge.psoc_motor_status import is_m33_motor_status_id, parse_m33_motor_status_frame
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.candump_motor_telemetry import parse_candump_line  # type: ignore[no-redef]
    from rehab_arm_psoc_bridge.psoc_motor_status import (  # type: ignore[no-redef]
        is_m33_motor_status_id,
        parse_m33_motor_status_frame,
    )


PSOC_HEARTBEAT_ID = 0x321
PSOC_STATUS_ID = 0x322
PSOC_TARGET_ID = 0x320
EXPECTED_M33_MOTOR_STATUS_IDS = list(range(0x330, 0x338))


def build_presence_report(path: str | Path) -> dict[str, object]:
    source = Path(path).expanduser()
    frame_count = 0
    parse_error_count = 0
    heartbeat_count = 0
    psoc_status_count = 0
    target_count = 0
    motor_status_count = 0
    valid_motor_status_count = 0
    invalid_motor_status_count = 0
    observed_ids: dict[str, int] = {}
    motor_status_ids: dict[str, int] = {}
    invalid_motor_status_samples: list[dict[str, object]] = []

    for line in source.read_text(encoding='utf-8', errors='replace').splitlines():
        if not line.strip():
            continue
        frame = parse_candump_line(line)
        if frame is None:
            parse_error_count += 1
            continue
        frame_count += 1
        can_id = int(frame['can_id'])
        can_id_hex = f'0x{can_id:03X}' if can_id <= 0x7FF else f'0x{can_id:X}'
        observed_ids[can_id_hex] = observed_ids.get(can_id_hex, 0) + 1
        if can_id == PSOC_HEARTBEAT_ID:
            heartbeat_count += 1
        elif can_id == PSOC_STATUS_ID:
            psoc_status_count += 1
        elif can_id == PSOC_TARGET_ID:
            target_count += 1
        if is_m33_motor_status_id(can_id):
            motor_status_count += 1
            motor_status_ids[can_id_hex] = motor_status_ids.get(can_id_hex, 0) + 1
            parsed = parse_m33_motor_status_frame(can_id, frame['data'])
            if parsed.get('valid') is True:
                valid_motor_status_count += 1
            else:
                invalid_motor_status_count += 1
                if len(invalid_motor_status_samples) < 5:
                    invalid_motor_status_samples.append({
                        'can_id': can_id_hex,
                        'data': parsed.get('raw_data'),
                        'detail': parsed.get('detail'),
                    })

    missing_expected_ids = [
        f'0x{can_id:03X}'
        for can_id in EXPECTED_M33_MOTOR_STATUS_IDS
        if f'0x{can_id:03X}' not in motor_status_ids
    ]
    errors: list[str] = []
    warnings: list[str] = []
    if frame_count == 0:
        errors.append('candump contains no parseable CAN frames')
    if heartbeat_count == 0:
        warnings.append('0x321 NanoPi heartbeat was not observed')
    if psoc_status_count == 0:
        warnings.append('0x322 M33/PSoC status was not observed')
    if valid_motor_status_count == 0:
        errors.append('no valid M33 motor status frames observed on 0x330~0x337')
    if target_count:
        errors.append('unexpected 0x320 target frames observed during readonly status check')
    if invalid_motor_status_count:
        warnings.append('invalid M33 motor status frames were observed')

    return {
        'schema_version': 'm33_motor_status_presence_report_v1',
        'ok': not errors,
        'source': str(source),
        'frame_count': frame_count,
        'parse_error_count': parse_error_count,
        'heartbeat_0x321_count': heartbeat_count,
        'psoc_status_0x322_count': psoc_status_count,
        'target_0x320_count': target_count,
        'm33_motor_status_count': motor_status_count,
        'valid_m33_motor_status_count': valid_motor_status_count,
        'invalid_m33_motor_status_count': invalid_motor_status_count,
        'observed_ids': dict(sorted(observed_ids.items())),
        'm33_motor_status_ids': dict(sorted(motor_status_ids.items())),
        'missing_expected_m33_motor_status_ids': missing_expected_ids,
        'invalid_m33_motor_status_samples': invalid_motor_status_samples,
        'errors': errors,
        'warnings': warnings,
        'control_boundary': 'candump_readonly_motor_status_presence_not_motion_permission',
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Check a candump log for readonly M33 0x330~0x337 motor status telemetry.',
    )
    parser.add_argument('candump_path')
    parser.add_argument('--pretty', action='store_true')
    parser.add_argument('--output', help='Optional path to write the JSON report.')
    args = parser.parse_args(argv)

    try:
        report = build_presence_report(args.candump_path)
    except Exception as exc:
        report = {
            'schema_version': 'm33_motor_status_presence_report_v1',
            'ok': False,
            'errors': [str(exc)],
            'control_boundary': 'candump_readonly_motor_status_presence_not_motion_permission',
        }
        text = json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None)
        print(text)
        return 2

    text = json.dumps(
        report,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
        sort_keys=args.pretty,
    )
    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + '\n', encoding='utf-8')
    print(text)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
