#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable


CommandRunner = Callable[[list[str], float], tuple[int, str, str]]


def default_runner(args: list[str], timeout_sec: float) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        return completed.returncode, completed.stdout, completed.stderr
    except Exception as exc:
        return 127, '', str(exc)


def command_available(name: str) -> bool:
    return shutil.which(name) is not None


def safe_json_command(
    args: list[str],
    runner: CommandRunner = default_runner,
    timeout_sec: float = 2.0,
) -> object | None:
    code, stdout, _stderr = runner(args, timeout_sec)
    if code != 0 or not stdout.strip():
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def discover_network_interfaces(sys_class_net: str | Path = '/sys/class/net') -> list[dict[str, object]]:
    root = Path(sys_class_net)
    if not root.exists():
        return []
    interfaces: list[dict[str, object]] = []
    for item in sorted(root.iterdir(), key=lambda path: path.name):
        if not item.is_dir() and not item.is_symlink():
            continue
        name = item.name
        if name == 'lo':
            continue
        state_path = item / 'operstate'
        address_path = item / 'address'
        iface_type = 'can' if name.startswith('can') else 'network'
        interfaces.append({
            'name': name,
            'kind': iface_type,
            'operstate': state_path.read_text(encoding='utf-8', errors='ignore').strip()
            if state_path.exists() else 'unknown',
            'address': address_path.read_text(encoding='utf-8', errors='ignore').strip()
            if address_path.exists() else '',
        })
    return interfaces


def discover_device_nodes(dev_dir: str | Path = '/dev') -> dict[str, list[str]]:
    root = Path(dev_dir)
    if not root.exists():
        return {'serial': [], 'camera': []}
    serial_patterns = ['ttyUSB*', 'ttyACM*', 'ttyAMA*', 'ttyS*']
    serial = sorted({
        f'/dev/{path.name}'
        for pattern in serial_patterns
        for path in root.glob(pattern)
    })
    camera = sorted(f'/dev/{path.name}' for path in root.glob('video*'))
    return {'serial': serial, 'camera': camera}


def discover_usb_devices(
    runner: CommandRunner = default_runner,
    timeout_sec: float = 2.0,
) -> list[dict[str, str]]:
    if not command_available('lsusb'):
        return []
    code, stdout, _stderr = runner(['lsusb'], timeout_sec)
    if code != 0:
        return []
    devices: list[dict[str, str]] = []
    for line in stdout.splitlines():
        text = line.strip()
        if text:
            devices.append({'kind': 'usb', 'description': text})
    return devices


def ros2_environment(
    runner: CommandRunner = default_runner,
    timeout_sec: float = 2.0,
) -> dict[str, object]:
    if not command_available('ros2'):
        return {'available': False, 'version_text': ''}
    code, stdout, stderr = runner(['ros2', '--version'], timeout_sec)
    return {
        'available': True,
        'version_text': (stdout or stderr).strip(),
        'version_command_ok': code == 0,
    }


def build_board_manifest(
    device_id: str,
    robot_id: str,
    sys_class_net: str | Path = '/sys/class/net',
    dev_dir: str | Path = '/dev',
    runner: CommandRunner = default_runner,
    now: Callable[[], float] = time.time,
) -> dict[str, object]:
    interfaces = discover_network_interfaces(sys_class_net)
    nodes = discover_device_nodes(dev_dir)
    usb_devices = discover_usb_devices(runner)
    ros2 = ros2_environment(runner)
    hostname = socket.gethostname()
    return {
        'schema_version': 'linux_board_manifest_v1',
        'device_id': device_id.strip() or hostname,
        'robot_id': robot_id.strip() or 'unassigned',
        'hostname': hostname,
        'online_state': 'online',
        'platform': {
            'system': platform.system(),
            'release': platform.release(),
            'machine': platform.machine(),
            'python': platform.python_version(),
        },
        'capabilities': {
            'network_interfaces': interfaces,
            'can_interfaces': [item for item in interfaces if item.get('kind') == 'can'],
            'serial_devices': nodes['serial'],
            'camera_devices': nodes['camera'],
            'usb_devices': usb_devices,
            'ros2': ros2,
        },
        'recommended_streams': [
            'motor_state',
            'sensor_state',
            'camera_keyframe',
            'simulation_readiness',
        ],
        'control_boundary': 'board_discovery_only_not_motion_permission',
        'ts_unix': int(now()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Build a read-only Linux board manifest for platform device onboarding.',
    )
    parser.add_argument('--device-id', default='', help='Stable board/device id. Defaults to hostname.')
    parser.add_argument('--robot-id', default='unassigned', help='Robot/project id to group this board under.')
    parser.add_argument('--output', default='', help='Optional JSON output path. Prints to stdout when omitted.')
    parser.add_argument('--pretty', action='store_true', help='Pretty-print JSON output.')
    parser.add_argument('--sys-class-net', default='/sys/class/net', help='Override for tests or unusual Linux roots.')
    parser.add_argument('--dev-dir', default='/dev', help='Override /dev root for tests.')
    args = parser.parse_args()

    manifest = build_board_manifest(
        device_id=args.device_id,
        robot_id=args.robot_id,
        sys_class_net=args.sys_class_net,
        dev_dir=args.dev_dir,
    )
    body = json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
        sort_keys=True,
    )
    if args.output:
        Path(args.output).expanduser().write_text(body + '\n', encoding='utf-8')
    else:
        print(body)
    return 0


if __name__ == '__main__':
    sys.exit(main())
