from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.bench_motion_sequence import build_motion_sequence_plan  # noqa: E402


class BenchMotionSequenceTests(unittest.TestCase):
    def test_build_default_motor7_sequence_plan(self) -> None:
        plan = build_motion_sequence_plan(
            joint_id=4,
            motor_id=7,
            degrees=[5.0, -5.0],
            rpm=1,
            hold_sec=2.0,
            iface='can0',
        )

        self.assertEqual(plan['schema_version'], 'rehab_arm_bench_motion_sequence_v1')
        self.assertEqual(plan['default_mode'], 'dry_run_no_can_access')
        self.assertIs(plan['onsite_required_for_execute'], True)
        target_commands = [item for item in plan['commands'] if item['kind'] == 'target']
        stop_commands = [item for item in plan['commands'] if item['kind'] == 'stop']
        self.assertEqual(len(target_commands), 2)
        self.assertEqual(len(stop_commands), 2)
        self.assertIn('--joint', target_commands[0]['argv'])
        self.assertIn('5', target_commands[0]['argv'])
        self.assertIn('-5', target_commands[1]['argv'])

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
