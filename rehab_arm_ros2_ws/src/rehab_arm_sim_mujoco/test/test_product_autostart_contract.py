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
        setup_script = (
            REPO_ROOT
            / 'deploy'
            / 'scripts'
            / 'setup_nanopi_can.sh'
        ).read_text(encoding='utf-8')

        self.assertIn('ExecStart=/usr/local/bin/start_nanopi_product_readonly.sh', service)
        self.assertIn('ExecStartPre=+/usr/local/bin/setup_nanopi_can.sh', service)
        self.assertIn('Environment=CAN_BITRATE=1000000', service)
        self.assertIn('Environment=RECOVER_MCP251XFD=1', service)
        self.assertIn('Environment=ROS_LOG_DIR=/home/pi/.ros/log', service)
        self.assertIn('Environment=SKIP_SOCKETCAN_SETUP=1', service)
        self.assertIn('User=pi', service)
        self.assertIn('export ROS_LOG_DIR', script)
        self.assertNotIn('$SUDO mkdir -p "$ROS_LOG_DIR"', script)
        self.assertNotIn('$SUDO chmod 0775 "$ROS_LOG_DIR"', script)
        self.assertIn('ip link set "$IFACE" type can bitrate "$CAN_BITRATE"', setup_script)
        self.assertIn('modprobe mcp251xfd', setup_script)
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
