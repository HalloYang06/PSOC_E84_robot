from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]


class ProductAutostartContractTests(unittest.TestCase):
    def test_nanopi_product_service_uses_readonly_start_script(self) -> None:
        service = (
            REPO_ROOT
            / 'deploy'
            / 'systemd'
            / 'rehab-arm-nanopi-readonly.service'
        ).read_text(encoding='utf-8')
        script = (
            REPO_ROOT
            / 'deploy'
            / 'scripts'
            / 'start_nanopi_product_readonly.sh'
        ).read_text(encoding='utf-8')

        self.assertIn('ExecStart=/usr/local/bin/start_nanopi_product_readonly.sh', service)
        self.assertIn('-p enable_target_tx:=false', script)
        self.assertNotIn('-p enable_target_tx:=true', script)
        self.assertNotIn('m33 target', script)
        self.assertNotIn('private speed', script)
        self.assertNotIn('private csp', script)

    def test_sim_host_service_is_shadow_only(self) -> None:
        service = (
            REPO_ROOT
            / 'deploy'
            / 'systemd'
            / 'rehab-arm-sim-host-shadow.service'
        ).read_text(encoding='utf-8')
        script = (
            REPO_ROOT
            / 'deploy'
            / 'scripts'
            / 'start_sim_host_medical_arm_shadow.sh'
        ).read_text(encoding='utf-8')

        self.assertIn('ExecStart=/usr/local/bin/start_sim_host_medical_arm_shadow.sh', service)
        self.assertIn('medical_arm_6dof_hardware_shadow.launch.py', script)
        self.assertNotIn('/arm_controller/joint_trajectory', script)
        self.assertNotIn('enable_target_tx:=true', script)


if __name__ == '__main__':
    unittest.main()
