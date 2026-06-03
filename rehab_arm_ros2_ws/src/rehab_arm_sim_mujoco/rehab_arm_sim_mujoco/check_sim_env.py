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

MEDICAL_ARM_6DOF_JOINT_NAMES = [
    'jian_hengxiang_joint',
    'jian_zongxiang_joint',
    'jian_xuanzhuan_joint',
    'zhou_zongxiang_joint',
    'wanbu_zongxiang_joint',
    'wanbu_hengxiang_joint',
]

DATA_TOOL_MODULES = [
    'rehab_arm_psoc_bridge.data_recording',
    'rehab_arm_psoc_bridge.build_manifest',
    'rehab_arm_psoc_bridge.sync_upload',
]

REMEDIATION_HINTS = {
    'rclpy': {
        'summary': 'ROS2 Python client is missing.',
        'commands': [
            'source /opt/ros/jazzy/setup.bash',
            'sudo apt install -y ros-jazzy-rclpy',
        ],
    },
    'mujoco': {
        'summary': 'MuJoCo Python package is missing; fallback simulation can still run unless strict mode is enabled.',
        'commands': [
            'python3 -m pip install --user mujoco',
            'python3 -c "import mujoco; print(mujoco.__version__)"',
        ],
    },
    'urdf': {
        'summary': 'Rehab arm URDF is missing from rehab_arm_description.',
        'commands': [
            'git checkout feature/rehab-arm-ros2-architecture',
            'ls rehab_arm_ros2_ws/src/rehab_arm_description/urdf/rehab_arm.urdf',
        ],
    },
    'sim_launch': {
        'summary': 'MuJoCo/fallback simulation launch file is missing.',
        'commands': [
            'ls rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/launch/sim.launch.py',
        ],
    },
    'medical_arm_6dof_mjcf': {
        'summary': 'medical_arm 6DOF MuJoCo MJCF model is missing.',
        'commands': [
            'ls rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/models/medical_arm_6dof.xml',
        ],
    },
    'medical_arm_6dof_schema': {
        'summary': 'medical_arm 6DOF joint/motor schema is missing.',
        'commands': [
            'ls rehab_arm_ros2_ws/src/rehab_arm_description/config/medical_arm_6dof_schema.yaml',
        ],
    },
    'medical_arm_6dof_shadow_launch': {
        'summary': 'medical_arm 6DOF standalone shadow launch file is missing.',
        'commands': [
            'ls rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/launch/medical_arm_6dof_shadow.launch.py',
        ],
    },
    'medical_arm_6dof_hardware_shadow_launch': {
        'summary': 'medical_arm 6DOF NanoPi hardware-shadow launch file is missing.',
        'commands': [
            'ls rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/launch/medical_arm_6dof_hardware_shadow.launch.py',
        ],
    },
    'sim_data_collection_launch': {
        'summary': 'Simulation data collection launch file is missing.',
        'commands': [
            'ls rehab_arm_ros2_ws/src/rehab_arm_bringup/launch/sim_data_collection.launch.py',
        ],
    },
    'data_tools': {
        'summary': 'Data collection/export tools are not importable; build the bridge package.',
        'commands': [
            'cd rehab_arm_ros2_ws',
            './build_ros2.sh --packages-select rehab_arm_psoc_bridge rehab_arm_sim_mujoco',
            'source install/setup.bash',
        ],
    },
}

NEXT_COMMANDS = {
    'ready_with_mujoco': [
        'cd rehab_arm_ros2_ws',
        './build_ros2.sh --packages-select rehab_arm_description rehab_arm_sim_mujoco rehab_arm_control rehab_arm_bringup',
        'source install/setup.bash',
        'ros2 launch rehab_arm_bringup sim_data_collection.launch.py',
    ],
    'medical_arm_6dof_shadow': [
        'cd rehab_arm_ros2_ws',
        './build_ros2.sh --packages-select rehab_arm_description rehab_arm_sim_mujoco',
        'source install/setup.bash',
        'ros2 launch rehab_arm_sim_mujoco medical_arm_6dof_shadow.launch.py',
        'ros2 topic echo --once /sim/medical_arm/joint_states sensor_msgs/msg/JointState',
    ],
    'medical_arm_6dof_hardware_shadow_readonly': [
        'NanoPi: ros2 run rehab_arm_psoc_bridge psoc_can_bridge_node.py --ros-args -p interface:=can0 -p enable_target_tx:=false -p log_heartbeat:=false',
        'Sim host: ros2 launch rehab_arm_sim_mujoco medical_arm_6dof_hardware_shadow.launch.py',
        'Sim host: ros2 topic echo --once /sim/medical_arm/joint_trajectory trajectory_msgs/msg/JointTrajectory',
        'Sim host: ros2 topic echo --once /sim/medical_arm/joint_states sensor_msgs/msg/JointState',
    ],
    'ready_with_fallback_sim': [
        'cd rehab_arm_ros2_ws',
        './build_ros2.sh --packages-select rehab_arm_description rehab_arm_sim_mujoco rehab_arm_control rehab_arm_bringup',
        'source install/setup.bash',
        'ros2 launch rehab_arm_bringup sim_data_collection.launch.py',
        'python3 -m pip install --user mujoco',
    ],
    'not_ready': [
        'cd rehab_arm_ros2_ws',
        './build_ros2.sh --packages-select rehab_arm_description rehab_arm_psoc_bridge rehab_arm_sim_mujoco',
        'source install/setup.bash',
        'ros2 run rehab_arm_sim_mujoco check_sim_env --pretty',
    ],
}

TOPIC_CONTRACT = {
    'trajectory_command': {
        'topic': '/arm_controller/joint_trajectory',
        'message_type': 'trajectory_msgs/msg/JointTrajectory',
        'direction': 'planner_to_sim_or_nanopi',
    },
    'joint_state': {
        'topic': '/joint_states',
        'message_type': 'sensor_msgs/msg/JointState',
        'direction': 'sim_or_hardware_to_ros',
    },
    'safety_state': {
        'topic': '/rehab_arm/safety_state',
        'message_type': 'std_msgs/msg/String',
        'direction': 'm33_or_sim_safety_to_ros',
    },
    'sensor_state': {
        'topic': '/rehab_arm/sensor_state',
        'message_type': 'std_msgs/msg/String',
        'direction': 'sensor_or_model_state_to_ros',
    },
    'vla_task_goal': {
        'topic': '/vla/task_goal',
        'message_type': 'std_msgs/msg/String',
        'direction': 'vla_task_planner_to_motion_planner',
    },
    'control_boundary': 'simulation_topic_contract_not_motion_permission',
}

MEDICAL_ARM_6DOF_TOPIC_CONTRACT = {
    'shadow_trajectory_command': {
        'topic': '/sim/medical_arm/joint_trajectory',
        'message_type': 'trajectory_msgs/msg/JointTrajectory',
        'direction': 'medical_arm_shadow_relay_or_planner_to_mujoco',
    },
    'shadow_joint_state': {
        'topic': '/sim/medical_arm/joint_states',
        'message_type': 'sensor_msgs/msg/JointState',
        'direction': 'mujoco_shadow_to_ros_or_server',
    },
    'shadow_safety_state': {
        'topic': '/sim/medical_arm/safety_state',
        'message_type': 'std_msgs/msg/String',
        'direction': 'mujoco_shadow_safety_to_ros_or_server',
    },
    'shadow_sensor_state': {
        'topic': '/sim/medical_arm/sensor_state',
        'message_type': 'std_msgs/msg/String',
        'direction': 'mujoco_shadow_sensor_state_to_ros_or_server',
    },
    'hardware_shadow_source': {
        'topic': '/joint_states',
        'message_type': 'sensor_msgs/msg/JointState',
        'direction': 'nanopi_or_legacy_bridge_to_shadow_relay',
    },
    'hardware_shadow_current_mapping': {
        'forearm_rotation_joint': 'jian_xuanzhuan_joint',
    },
    'unconnected_joint_policy': 'publish_full_6dof_target_with_explicit_placeholder_positions',
    'control_boundary': 'shadow_simulation_not_formal_motion_permission',
}


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


def build_missing_actions(checks: dict[str, object], strict_mujoco: bool) -> list[dict[str, object]]:
    actions: list[dict[str, object]] = []
    for key in (
        'rclpy',
        'mujoco',
        'urdf',
        'sim_launch',
        'medical_arm_6dof_mjcf',
        'medical_arm_6dof_schema',
        'medical_arm_6dof_shadow_launch',
        'medical_arm_6dof_hardware_shadow_launch',
        'sim_data_collection_launch',
    ):
        item = checks[key]
        if not isinstance(item, dict) or item.get('ok'):
            continue
        if key == 'mujoco' and not strict_mujoco:
            severity = 'optional'
        else:
            severity = 'required'
        hint = REMEDIATION_HINTS[key]
        actions.append({
            'id': key,
            'severity': severity,
            'summary': hint['summary'],
            'commands': hint['commands'],
        })

    data_tools = checks.get('data_tools', {})
    if isinstance(data_tools, dict):
        missing_data_modules = [
            name for name, item in data_tools.items()
            if isinstance(item, dict) and not item.get('ok')
        ]
        if missing_data_modules:
            hint = REMEDIATION_HINTS['data_tools']
            actions.append({
                'id': 'data_tools',
                'severity': 'required',
                'summary': hint['summary'],
                'missing_modules': missing_data_modules,
                'commands': hint['commands'],
            })
    return actions


def build_sim_env_report(
    workspace_root: str | Path | None = None,
    import_checker: Callable[[str], bool] = default_import_checker,
    strict_mujoco: bool = False,
) -> dict[str, object]:
    root = Path(workspace_root).resolve() if workspace_root else find_workspace_root()
    add_source_packages_to_path(root)

    urdf_path = root / 'src' / 'rehab_arm_description' / 'urdf' / 'rehab_arm.urdf'
    medical_arm_schema_path = root / 'src' / 'rehab_arm_description' / 'config' / 'medical_arm_6dof_schema.yaml'
    sim_launch_path = root / 'src' / 'rehab_arm_sim_mujoco' / 'launch' / 'sim.launch.py'
    medical_arm_mjcf_path = root / 'src' / 'rehab_arm_sim_mujoco' / 'models' / 'medical_arm_6dof.xml'
    medical_arm_shadow_launch_path = (
        root / 'src' / 'rehab_arm_sim_mujoco' / 'launch' / 'medical_arm_6dof_shadow.launch.py'
    )
    medical_arm_hardware_shadow_launch_path = (
        root / 'src' / 'rehab_arm_sim_mujoco' / 'launch' / 'medical_arm_6dof_hardware_shadow.launch.py'
    )
    collection_launch_path = root / 'src' / 'rehab_arm_bringup' / 'launch' / 'sim_data_collection.launch.py'

    checks: dict[str, object] = {
        'rclpy': make_import_check('rclpy', import_checker, required=True),
        'mujoco': make_import_check('mujoco', import_checker, required=strict_mujoco),
        'urdf': make_file_check(urdf_path, required=True),
        'sim_launch': make_file_check(sim_launch_path, required=True),
        'medical_arm_6dof_mjcf': make_file_check(medical_arm_mjcf_path, required=True),
        'medical_arm_6dof_schema': make_file_check(medical_arm_schema_path, required=True),
        'medical_arm_6dof_shadow_launch': make_file_check(medical_arm_shadow_launch_path, required=True),
        'medical_arm_6dof_hardware_shadow_launch': make_file_check(
            medical_arm_hardware_shadow_launch_path,
            required=True,
        ),
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
        checks['medical_arm_6dof_mjcf'],  # type: ignore[index]
        checks['medical_arm_6dof_schema'],  # type: ignore[index]
        checks['medical_arm_6dof_shadow_launch'],  # type: ignore[index]
        checks['medical_arm_6dof_hardware_shadow_launch'],  # type: ignore[index]
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

    missing_actions = build_missing_actions(checks, strict_mujoco)

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
            'profile': 'legacy_5dof',
            'status': 'legacy_contract_for_existing_bridge_and_smoke_tests',
        },
        'medical_arm_6dof_contract': {
            'profile': 'medical_arm_6dof',
            'count': len(MEDICAL_ARM_6DOF_JOINT_NAMES),
            'names': MEDICAL_ARM_6DOF_JOINT_NAMES,
            'mjcf_path': str(medical_arm_mjcf_path),
            'schema_path': str(medical_arm_schema_path),
            'shadow_launch': str(medical_arm_shadow_launch_path),
            'hardware_shadow_launch': str(medical_arm_hardware_shadow_launch_path),
            'trajectory_topic': '/sim/medical_arm/joint_trajectory',
            'state_topic': '/sim/medical_arm/joint_states',
            'safety_state_topic': '/sim/medical_arm/safety_state',
            'sensor_state_topic': '/sim/medical_arm/sensor_state',
            'status': 'current_mainline_shadow_simulation_contract',
        },
        'topic_contract': TOPIC_CONTRACT,
        'medical_arm_6dof_topic_contract': MEDICAL_ARM_6DOF_TOPIC_CONTRACT,
        'safety_note': (
            'This is a read-only simulation environment check. It does not open CAN, '
            'does not send 0x320/0x321 frames, and does not command M33 or motors.'
        ),
        'missing_actions': missing_actions,
        'next_commands': NEXT_COMMANDS[readiness],
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
    parser.add_argument(
        '--output',
        help='Optional path to write the JSON report for platform upload or handoff.',
    )
    args = parser.parse_args(argv)

    report = build_sim_env_report(args.workspace_root, strict_mujoco=args.strict_mujoco)
    output = json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=args.pretty)
    if args.output:
        output_path = Path(args.output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output + '\n', encoding='utf-8')
    print(output)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
