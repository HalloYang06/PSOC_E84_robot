#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import sys
from pathlib import Path
from typing import Callable


SCHEMA_VERSION = 'rehab_arm_sim_env_check_v1'

JOINT_NAMES = [
    'shoulder_lift_joint',
    'elbow_lift_joint',
    'shoulder_abduction_joint',
    'upper_arm_rotation_joint',
    'forearm_rotation_joint',
]

DATA_TOOL_MODULES = [
    'rehab_arm_psoc_bridge.data_recording',
    'rehab_arm_psoc_bridge.build_manifest',
    'rehab_arm_psoc_bridge.sync_upload',
]


def default_import_checker(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def find_workspace_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__).resolve()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / 'src' / 'rehab_arm_description').exists():
            return candidate
        if candidate.name == 'rehab_arm_ros2_ws' and (candidate / 'src').exists():
            return candidate
    return Path.cwd().resolve()


def add_source_packages_to_path(workspace_root: Path) -> None:
    src_dir = workspace_root / 'src'
    for package_dir in src_dir.glob('*'):
        if package_dir.is_dir() and str(package_dir) not in sys.path:
            sys.path.insert(0, str(package_dir))


def make_file_check(path: Path, required: bool = True) -> dict[str, object]:
    return {
        'ok': path.exists(),
        'required': required,
        'path': str(path),
    }


def make_import_check(
    module_name: str,
    import_checker: Callable[[str], bool],
    required: bool = True,
) -> dict[str, object]:
    ok = import_checker(module_name)
    return {
        'ok': ok,
        'required': required,
        'module': module_name,
    }


def build_sim_env_report(
    workspace_root: str | Path | None = None,
    import_checker: Callable[[str], bool] = default_import_checker,
    strict_mujoco: bool = False,
) -> dict[str, object]:
    root = Path(workspace_root).resolve() if workspace_root else find_workspace_root()
    add_source_packages_to_path(root)

    urdf_path = root / 'src' / 'rehab_arm_description' / 'urdf' / 'rehab_arm.urdf'
    sim_launch_path = root / 'src' / 'rehab_arm_sim_mujoco' / 'launch' / 'sim.launch.py'
    collection_launch_path = root / 'src' / 'rehab_arm_bringup' / 'launch' / 'sim_data_collection.launch.py'

    checks: dict[str, object] = {
        'rclpy': make_import_check('rclpy', import_checker, required=True),
        'mujoco': make_import_check('mujoco', import_checker, required=strict_mujoco),
        'urdf': make_file_check(urdf_path, required=True),
        'sim_launch': make_file_check(sim_launch_path, required=True),
        'sim_data_collection_launch': make_file_check(collection_launch_path, required=True),
        'data_tools': {
            module_name: make_import_check(module_name, import_checker, required=True)
            for module_name in DATA_TOOL_MODULES
        },
    }

    required_checks: list[dict[str, object]] = [
        checks['rclpy'],  # type: ignore[index]
        checks['urdf'],  # type: ignore[index]
        checks['sim_launch'],  # type: ignore[index]
        checks['sim_data_collection_launch'],  # type: ignore[index]
    ]
    required_checks.extend(checks['data_tools'].values())  # type: ignore[union-attr]
    if strict_mujoco:
        required_checks.append(checks['mujoco'])  # type: ignore[arg-type]

    errors = [
        f"{item.get('module') or item.get('path')} is required but not available"
        for item in required_checks
        if not item.get('ok')
    ]

    mujoco_ok = bool(checks['mujoco']['ok'])  # type: ignore[index]
    if errors:
        readiness = 'not_ready'
    elif mujoco_ok:
        readiness = 'ready_with_mujoco'
    else:
        readiness = 'ready_with_fallback_sim'

    return {
        'schema_version': SCHEMA_VERSION,
        'ok': not errors,
        'readiness': readiness,
        'workspace_root': str(root),
        'python': {
            'version': sys.version.split()[0],
            'executable': sys.executable,
            'platform': platform.platform(),
        },
        'checks': checks,
        'joint_contract': {
            'count': len(JOINT_NAMES),
            'names': JOINT_NAMES,
            'trajectory_topic': '/arm_controller/joint_trajectory',
            'state_topic': '/joint_states',
        },
        'safety_note': (
            'This is a read-only simulation environment check. It does not open CAN, '
            'does not send 0x320/0x321 frames, and does not command M33 or motors.'
        ),
        'errors': errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Check rehab arm ROS2/MuJoCo simulation environment.')
    parser.add_argument('--workspace-root', help='Path to rehab_arm_ros2_ws. Defaults to auto-detection.')
    parser.add_argument('--pretty', action='store_true', help='Pretty-print JSON output.')
    parser.add_argument(
        '--strict-mujoco',
        action='store_true',
        help='Fail when the mujoco Python package is missing instead of allowing fallback simulation.',
    )
    args = parser.parse_args(argv)

    report = build_sim_env_report(args.workspace_root, strict_mujoco=args.strict_mujoco)
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=args.pretty))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
