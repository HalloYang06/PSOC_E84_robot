from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]


class SystemArchitectureContractTests(unittest.TestCase):
    def test_system_architecture_keeps_single_mainline(self) -> None:
        architecture = (
            REPO_ROOT
            / 'docs'
            / 'REHAB_ARM_SYSTEM_ARCHITECTURE.md'
        ).read_text(encoding='utf-8')

        self.assertIn('## 2.0.1 整机架构地基合同', architecture)
        self.assertIn('JointTrajectory -> NanoPi -> M33 -> 电机', architecture)
        self.assertIn('不能新增“服务器直控电机”', architecture)
        self.assertIn('M55 小模型', architecture)
        self.assertIn('M33 BLE 到 App', architecture)
        self.assertIn('NanoPi 到服务器', architecture)
        self.assertIn('Linux 仿真主机无线 ROS', architecture)
        self.assertIn('side-channel', architecture)
        self.assertIn('以本节为准', architecture)

    def test_integration_guide_reuses_shared_contracts(self) -> None:
        integration = (
            REPO_ROOT
            / 'docs'
            / 'INTEGRATION_GUIDE.md'
        ).read_text(encoding='utf-8')

        self.assertIn('## 1.1 当前主线和旁线对接纪律', integration)
        self.assertIn('M55 只输出小模型编号', integration)
        self.assertIn('M33 BLE 到 App', integration)
        self.assertIn('NanoPi 到服务器', integration)
        self.assertIn('无线 ROS', integration)
        self.assertIn('PATIENT_DEVICE_PROFILE_PROTOCOL_V1.md', integration)
        self.assertIn('PSOC_CAN_PROTOCOL_V1.md', integration)
        self.assertIn('medical_arm_6dof_schema.yaml', integration)
        self.assertIn('M55_MODEL_RESULT_PROTOCOL_V1.md', integration)
        self.assertIn('/rehab_arm/model_state', integration)

    def test_m55_model_result_protocol_is_suggestion_only(self) -> None:
        protocol = (
            REPO_ROOT
            / 'docs'
            / 'M55_MODEL_RESULT_PROTOCOL_V1.md'
        ).read_text(encoding='utf-8')
        server_sync = (
            REPO_ROOT
            / 'docs'
            / 'SERVER_SYNC_API_DRAFT.md'
        ).read_text(encoding='utf-8')

        self.assertIn('/rehab_arm/model_state', protocol)
        self.assertIn('rehab_arm_model_state_v1', protocol)
        self.assertIn('model_suggestion_only_not_motion_permission', protocol)
        self.assertIn('不得让 M55 的 `result_code` 直接映射成 `0x320`', protocol)
        self.assertIn('M55_MODEL_RESULT_PROTOCOL_V1.md', server_sync)
        self.assertIn('/model-state', server_sync)
        self.assertIn('model_suggestion_only_not_motion_permission', server_sync)


if __name__ == '__main__':
    unittest.main()
