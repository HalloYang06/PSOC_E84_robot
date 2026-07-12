from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_DIR))

from rehab_arm_sim_mujoco.check_sim_env import SCHEMA_VERSION  # noqa: E402
from rehab_arm_sim_mujoco.upload_sim_readiness import (  # noqa: E402
    CONTROL_BOUNDARY,
    build_upload_plan,
    execute_upload_plan,
    load_report,
)


class FakeResponse:
    status = 200

    def read(self) -> bytes:
        return b'{"data":{"ok":true}}'


def minimal_report() -> dict[str, object]:
    return {
        'schema_version': SCHEMA_VERSION,
        'ok': True,
        'readiness': 'ready_with_fallback_sim',
        'joint_contract': {
            'count': 5,
            'names': [
                'shoulder_lift_joint',
                'elbow_lift_joint',
                'shoulder_abduction_joint',
                'upper_arm_rotation_joint',
                'forearm_rotation_joint',
            ],
        },
        'safety_note': 'read-only simulation environment check',
        'errors': [],
    }


class UploadSimReadinessTests(unittest.TestCase):
    def test_load_report_requires_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'sim_readiness_report.json'
            path.write_text(json.dumps(minimal_report()), encoding='utf-8')

            report = load_report(path)

        self.assertEqual(report['schema_version'], SCHEMA_VERSION)

    def test_build_upload_plan_is_data_only(self) -> None:
        plan = build_upload_plan(
            minimal_report(),
            'http://server.local/api/rehab-arm/v1/',
            'rehab-arm-alpha',
            'nanopi-m5',
        )

        self.assertEqual(plan['control_boundary'], CONTROL_BOUNDARY)
        self.assertEqual(
            plan['request']['url'],  # type: ignore[index]
            'http://server.local/api/rehab-arm/v1/devices/nanopi-m5/simulation-readiness',
        )
        payload = plan['request']['json']  # type: ignore[index]
        self.assertEqual(payload['device_id'], 'nanopi-m5')
        self.assertEqual(payload['report']['readiness'], 'ready_with_fallback_sim')

    def test_execute_upload_plan_posts_json_with_fake_opener(self) -> None:
        seen: list[str] = []

        def opener(req, timeout):
            seen.append(f'{req.get_method()} {req.full_url} {timeout} {req.headers["Content-type"]}')
            payload = json.loads(req.data.decode('utf-8'))
            self.assertEqual(payload['device_id'], 'nanopi-m5')
            return FakeResponse()

        result = execute_upload_plan(
            build_upload_plan(minimal_report(), 'http://server.local/api/rehab-arm/v1', 'rehab-arm-alpha', 'nanopi-m5'),
            timeout_sec=2.5,
            opener=opener,
        )

        self.assertIs(result['ok'], True)
        self.assertEqual(result['control_boundary'], CONTROL_BOUNDARY)
        self.assertEqual(seen, ['POST http://server.local/api/rehab-arm/v1/devices/nanopi-m5/simulation-readiness 2.5 application/json'])

    def test_cli_dry_run_prints_plan_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'sim_readiness_report.json'
            path.write_text(json.dumps(minimal_report()), encoding='utf-8')

            result = subprocess.run(
                [
                    sys.executable,
                    str(PACKAGE_DIR / 'rehab_arm_sim_mujoco' / 'upload_sim_readiness.py'),
                    str(path),
                    '--device-id',
                    'nanopi-m5',
                    '--base-url',
                    'http://server.local/api/rehab-arm/v1',
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['schema_version'], 'rehab_arm_sim_readiness_upload_plan_v1')
        self.assertEqual(payload['control_boundary'], CONTROL_BOUNDARY)


if __name__ == '__main__':
    unittest.main()
