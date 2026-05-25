#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rehab_arm_psoc_bridge.data_recording import (
        JOINT_STATE_CSV_FIELDS,
        MOTOR_STATE_CSV_FIELDS,
        load_jsonl_records,
        make_joint_state_csv_rows,
        make_motor_state_csv_rows,
        write_csv_rows,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rehab_arm_psoc_bridge.data_recording import (
        JOINT_STATE_CSV_FIELDS,
        MOTOR_STATE_CSV_FIELDS,
        load_jsonl_records,
        make_joint_state_csv_rows,
        make_motor_state_csv_rows,
        write_csv_rows,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description='Export rehab arm JSONL joint and motor states to CSV.')
    parser.add_argument('path', help='Path to a recorder JSONL file')
    parser.add_argument(
        '--output-dir',
        default='',
        help='Directory for CSV files. Defaults to <jsonl parent>/<jsonl stem>_csv.',
    )
    args = parser.parse_args()

    source = Path(args.path).expanduser()
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else source.parent / f'{source.stem}_csv'

    try:
        records = load_jsonl_records(source)
        joint_rows = make_joint_state_csv_rows(records)
        motor_rows = make_motor_state_csv_rows(records)
        joint_path = output_dir / 'joint_states.csv'
        motor_path = output_dir / 'motor_states.csv'
        write_csv_rows(joint_path, joint_rows, JOINT_STATE_CSV_FIELDS)
        write_csv_rows(motor_path, motor_rows, MOTOR_STATE_CSV_FIELDS)
    except Exception as exc:
        print(json.dumps({'ok': False, 'errors': [str(exc)]}, ensure_ascii=False))
        return 2

    print(json.dumps({
        'schema_version': 'rehab_arm_csv_export_v1',
        'ok': True,
        'source_path': str(source),
        'output_dir': str(output_dir),
        'joint_states_csv': str(joint_path),
        'joint_state_row_count': len(joint_rows),
        'motor_states_csv': str(motor_path),
        'motor_state_row_count': len(motor_rows),
    }, ensure_ascii=False, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
