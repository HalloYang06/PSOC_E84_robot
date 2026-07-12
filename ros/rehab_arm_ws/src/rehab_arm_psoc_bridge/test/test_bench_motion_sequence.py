from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.bench_motion_sequence import (  # noqa: E402
    MOTOR_PROFILES,
    build_motion_sequence_plan,
)


class BenchMotionSequenceTests(unittest.TestCase):
    def test_build_default_motor7_sequence_plan(self) -> None:
        plan = build_motion_sequence_plan(
            motor_id=7,
            degrees=[5.0, -5.0],
            rpm=1,
            hold_sec=2.0,
            iface='can0',
        )

        self.assertEqual(plan['schema_version'], 'rehab_arm_bench_motion_sequence_v1')
        self.assertEqual(plan['default_mode'], 'dry_run_no_can_access')
        self.assertIs(plan['onsite_required_for_execute'], True)
        self.assertEqual(plan['joint_id'], 4)
        self.assertEqual(plan['motor_profile']['model'], 'EL05')
        self.assertEqual(sorted(int(key) for key in plan['available_motor_profiles']), [3, 4, 5, 6, 7])
        self.assertEqual(plan['execution_allowed_motor_ids'], [3, 7])
        target_commands = [item for item in plan['commands'] if item['kind'] == 'target']
        stop_commands = [item for item in plan['commands'] if item['kind'] == 'stop']
        self.assertEqual(len(target_commands), 2)
        self.assertEqual(len(stop_commands), 2)
        self.assertIn('--joint', target_commands[0]['argv'])
        self.assertIn('5', target_commands[0]['argv'])
        self.assertIn('-5', target_commands[1]['argv'])

    def test_all_known_motors_have_profiles_but_only_3_and_7_execute(self) -> None:
        self.assertEqual(sorted(MOTOR_PROFILES), [3, 4, 5, 6, 7])
        self.assertEqual(MOTOR_PROFILES[3]['joint_id'], 0)
        self.assertEqual(MOTOR_PROFILES[4]['model'], 'RS00')
        self.assertEqual(MOTOR_PROFILES[5]['model'], 'RS00')
        self.assertEqual(MOTOR_PROFILES[6]['model'], 'EL05')
        self.assertEqual(MOTOR_PROFILES[7]['joint_id'], 4)

    def test_cli_refuses_execute_without_onsite_confirmation(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parents[1] / 'rehab_arm_psoc_bridge' / 'bench_motion_sequence.py'),
                '--execute',
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['error'], '--execute requires --confirm-onsite')
        self.assertEqual(payload['control_boundary'], 'formal_m33_path_requires_onsite_confirmation')

    def test_cli_refuses_execute_for_motor4_even_with_onsite_confirmation(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parents[1] / 'rehab_arm_psoc_bridge' / 'bench_motion_sequence.py'),
                '--motor-id',
                '4',
                '--execute',
                '--confirm-onsite',
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertIn('not in execution allowlist', payload['error'])

    def test_cli_list_motors_outputs_profiles(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parents[1] / 'rehab_arm_psoc_bridge' / 'bench_motion_sequence.py'),
                '--list-motors',
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(sorted(payload['profiles']), ['3', '4', '5', '6', '7'])
        self.assertEqual(payload['execution_allowed_motor_ids'], [3, 7])

    def test_cli_dry_run_outputs_plan(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parents[1] / 'rehab_arm_psoc_bridge' / 'bench_motion_sequence.py'),
                '--degrees',
                '10,-10',
                '--pretty',
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['degrees'], [10.0, -10.0])
        self.assertEqual(payload['ok'], True)


if __name__ == '__main__':
    unittest.main()
