from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.check_server_quality_gate import (  # noqa: E402
    build_quality_gate_check,
    load_server_dashboard,
)


class FakeResponse:
    status = 200

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode('utf-8')


class CheckServerQualityGateTests(unittest.TestCase):
    def test_build_quality_gate_check_accepts_ready_device(self) -> None:
        dashboard = {
            'devices': [
                {
                    'device_id': 'nanopi-quality-demo',
                    'robot_id': 'rehab-arm-alpha',
                    'data_quality': {
                        'annotation_ready': True,
                        'control_boundary': 'data_quality_only_not_motion_permission',
                        'blocking_reasons': [],
                        'latest_session': {
                            'session_id': 'quality_demo',
                            'quality_report_ok': True,
                            'moving_joint_count': 1,
                            'motor_entry_count_min': 1,
                            'motor_entry_count_max': 1,
                            'quality_criteria': {'min_moving_joints': 1},
                        },
                    },
                },
            ],
        }

        result = build_quality_gate_check(dashboard, 'nanopi-quality-demo')

        self.assertIs(result['ok'], True)
        self.assertEqual(result['latest_session_id'], 'quality_demo')
        self.assertEqual(result['quality_criteria']['min_moving_joints'], 1)
        self.assertEqual(result['control_boundary'], 'data_quality_only_not_motion_permission')

    def test_build_quality_gate_check_reports_blocking_reason(self) -> None:
        dashboard = {
            'devices': [
                {
                    'device_id': 'nanopi-m5',
                    'robot_id': 'rehab-arm-alpha',
                    'data_quality': {
                        'annotation_ready': False,
                        'control_boundary': 'data_quality_only_not_motion_permission',
                        'blocking_reasons': ['moving joint count 0 below required 1'],
                        'latest_session': {
                            'session_id': 'static-check',
                            'quality_report_ok': False,
                            'moving_joint_count': 0,
                        },
                    },
                },
            ],
        }

        result = build_quality_gate_check(dashboard, 'nanopi-m5')

        self.assertIs(result['ok'], False)
        self.assertIn('annotation_ready is false', result['errors'])
        self.assertIn('latest quality_report_ok is false', result['errors'])
        self.assertIn('moving joint count 0 below required 1', result['errors'])

    def test_load_server_dashboard_uses_get_dashboard_endpoint(self) -> None:
        seen: list[str] = []

        def opener(req, timeout):
            seen.append(f'{req.get_method()} {req.full_url} {timeout}')
            return FakeResponse({'data': {'devices': []}})

        dashboard = load_server_dashboard('http://server.local/api/rehab-arm/v1/', timeout_sec=2.5, opener=opener)

        self.assertEqual(dashboard, {'devices': []})
        self.assertEqual(seen, ['GET http://server.local/api/rehab-arm/v1/devices/dashboard 2.5'])


if __name__ == '__main__':
    unittest.main()
