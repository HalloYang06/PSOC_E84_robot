#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path


DEFAULT_MASTER = '/home/pi/nanopi_can_master.py'
CONTROL_BOUNDARY = 'formal_m33_path_requires_onsite_confirmation'


def build_motion_sequence_plan(
    *,
    joint_id: int,
    motor_id: int,
    degrees: list[float],
    rpm: int,
    hold_sec: float,
    iface: str,
    master_path: str = DEFAULT_MASTER,
) -> dict[str, object]:
    commands: list[dict[str, object]] = []
    commands.append({
        'kind': 'precheck_heartbeat',
        'argv': ['python3', master_path, 'heartbeat', '--iface', iface, '--seq', '51', '--wait', '0.3'],
    })
    for index, deg in enumerate(degrees, start=1):
        commands.append({
            'kind': 'target',
            'step': index,
            'target_deg': deg,
            'argv': [
                'python3', master_path, 'm33', 'target',
                '--iface', iface,
                '--joint', str(joint_id),
                '--deg', format_float(deg),
                '--rpm', str(rpm),
                '--torque-ma', '0',
                '--wait', '0.5',
            ],
        })
        commands.append({
            'kind': 'hold',
            'step': index,
            'seconds': hold_sec,
        })
        commands.append({
            'kind': 'stop',
            'step': index,
            'argv': [
                'python3', master_path, 'm33', 'stop',
                '--iface', iface,
                '--joint', str(joint_id),
                '--wait', '0.3',
            ],
        })
    commands.append({
        'kind': 'postcheck_heartbeat',
        'argv': ['python3', master_path, 'heartbeat', '--iface', iface, '--seq', '52', '--wait', '0.3'],
    })
    return {
        'schema_version': 'rehab_arm_bench_motion_sequence_v1',
        'motor_id': motor_id,
        'joint_id': joint_id,
        'iface': iface,
        'rpm': rpm,
        'hold_sec': hold_sec,
        'degrees': degrees,
        'control_boundary': CONTROL_BOUNDARY,
        'default_mode': 'dry_run_no_can_access',
        'onsite_required_for_execute': True,
        'commands': commands,
        'safety_notes': [
            'Run only on an unloaded bench with a human on site watching the mechanism.',
            'Do not run while worn by a patient.',
            'Use motion_test_report.py on the candump log before increasing angle or speed.',
        ],
    }


def format_float(value: float) -> str:
    text = f'{value:.6f}'.rstrip('0').rstrip('.')
    return text or '0'


def run_motion_sequence(plan: dict[str, object]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for command in plan['commands']:
        if not isinstance(command, dict):
            continue
        kind = command.get('kind')
        if kind == 'hold':
            seconds = float(command['seconds'])
            time.sleep(seconds)
            results.append({'kind': kind, 'ok': True, 'seconds': seconds})
            continue
        argv = command.get('argv')
        if not isinstance(argv, list):
            results.append({'kind': kind, 'ok': False, 'error': 'missing argv'})
            continue
        completed = subprocess.run(
            [str(item) for item in argv],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        results.append({
            'kind': kind,
            'argv': argv,
            'returncode': completed.returncode,
            'ok': completed.returncode == 0,
            'stdout': completed.stdout,
            'stderr': completed.stderr,
        })
        if completed.returncode != 0:
            break
    return results


def parse_degrees(text: str) -> list[float]:
    values = [float(item.strip()) for item in text.split(',') if item.strip()]
    if not values:
        raise argparse.ArgumentTypeError('at least one degree value is required')
    return values


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Generate or execute a guarded bench motion sequence through the formal M33 path.',
    )
    parser.add_argument('--joint-id', type=int, default=4)
    parser.add_argument('--motor-id', type=int, default=7)
    parser.add_argument('--degrees', type=parse_degrees, default=parse_degrees('5,-5'))
    parser.add_argument('--rpm', type=int, default=1)
    parser.add_argument('--hold-sec', type=float, default=2.0)
    parser.add_argument('--iface', default='can0')
    parser.add_argument('--master-path', default=DEFAULT_MASTER)
    parser.add_argument('--execute', action='store_true', help='Actually run the generated commands.')
    parser.add_argument(
        '--confirm-onsite',
        action='store_true',
        help='Required with --execute to confirm a human is physically watching the bench.',
    )
    parser.add_argument('--pretty', action='store_true')
    parser.add_argument('--output', help='Optional path to write the plan/result JSON.')
    args = parser.parse_args(argv)

    plan = build_motion_sequence_plan(
        joint_id=args.joint_id,
        motor_id=args.motor_id,
        degrees=args.degrees,
        rpm=args.rpm,
        hold_sec=args.hold_sec,
        iface=args.iface,
        master_path=args.master_path,
    )
    if args.execute:
        if not args.confirm_onsite:
            plan['ok'] = False
            plan['error'] = '--execute requires --confirm-onsite'
            return emit(plan, args.pretty, args.output, returncode=2)
        plan['execution_results'] = run_motion_sequence(plan)
        plan['ok'] = all(item.get('ok') is True for item in plan['execution_results'])
        return emit(plan, args.pretty, args.output, returncode=0 if plan['ok'] else 1)

    plan['ok'] = True
    return emit(plan, args.pretty, args.output, returncode=0)


def emit(payload: dict[str, object], pretty: bool, output: str | None, returncode: int) -> int:
    text = json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None, sort_keys=pretty)
    if output:
        path = Path(output).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + '\n', encoding='utf-8')
    print(text)
    return returncode


if __name__ == '__main__':
    raise SystemExit(main())
