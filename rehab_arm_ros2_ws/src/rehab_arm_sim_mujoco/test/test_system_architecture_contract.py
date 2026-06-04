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

    def test_m33_m55_ipc_and_ble_foundation_reuses_existing_paths(self) -> None:
        foundation = (
            REPO_ROOT
            / 'docs'
            / 'M33_M55_IPC_BLE_FOUNDATION.md'
        ).read_text(encoding='utf-8')
        deployment = (
            REPO_ROOT
            / 'docs'
            / 'M55_MODEL_DEPLOYMENT_GUIDE.md'
        ).read_text(encoding='utf-8')
        architecture = (
            REPO_ROOT
            / 'docs'
            / 'REHAB_ARM_SYSTEM_ARCHITECTURE.md'
        ).read_text(encoding='utf-8')

        self.assertIn('GitHub `M55` 分支', foundation)
        self.assertIn('MTB-IPC queue', foundation)
        self.assertIn('.ipc_stream_shared', foundation)
        self.assertIn('0x261C0000', foundation)
        self.assertIn('NUS', foundation)
        self.assertIn('App 不允许发 CAN', foundation)
        self.assertIn('不要新建第二套 M33/M55 通讯', foundation)

        self.assertIn('TensorflowLiteMicro-latest', deployment)
        self.assertIn('model_manager_load_tflm_model', deployment)
        self.assertIn('MODEL_SLOT_EMG', deployment)
        self.assertIn('m33_m55_comm_publish', deployment)
        self.assertIn('model_suggestion_only_not_motion_permission', deployment)

        self.assertIn('M33_M55_IPC_BLE_FOUNDATION.md', architecture)
        self.assertIn('M55_MODEL_DEPLOYMENT_GUIDE.md', architecture)

    def test_current_github_briefing_is_the_public_entrypoint(self) -> None:
        briefing_path = REPO_ROOT / 'docs' / 'CURRENT_PROJECT_BRIEFING.md'
        video_frame_path = REPO_ROOT / 'docs' / 'assets' / 'medical_arm_video_frame.png'
        readme = (REPO_ROOT / 'README.md').read_text(encoding='utf-8')
        briefing = briefing_path.read_text(encoding='utf-8')

        self.assertTrue(briefing_path.exists(), briefing_path)
        self.assertTrue(video_frame_path.exists(), video_frame_path)
        self.assertGreater(video_frame_path.stat().st_size, 100_000)

        self.assertIn('CURRENT_PROJECT_BRIEFING.md', readme)
        self.assertIn('docs/assets/medical_arm_video_frame.png', readme)
        self.assertIn('GitHub 仓库导览', briefing)
        self.assertIn('GitHub 分支', briefing)
        self.assertIn('feature/rehab-arm-ros2-architecture', briefing)
        self.assertIn('`M33`', briefing)
        self.assertIn('`M55`', briefing)
        self.assertIn('`C8T6`', briefing)
        self.assertIn('`APP`', briefing)
        self.assertIn('不是生成图', briefing)

    def test_current_briefing_links_model_files_and_preserves_motion_boundary(self) -> None:
        briefing = (
            REPO_ROOT
            / 'docs'
            / 'CURRENT_PROJECT_BRIEFING.md'
        ).read_text(encoding='utf-8')
        schema = (
            REPO_ROOT
            / 'rehab_arm_ros2_ws'
            / 'src'
            / 'rehab_arm_description'
            / 'config'
            / 'medical_arm_6dof_schema.yaml'
        ).read_text(encoding='utf-8')

        self.assertIn('rehab_arm_description/urdf/rehab_arm.urdf', briefing)
        self.assertIn('rehab_arm_sim_mujoco/models/medical_arm_6dof.xml', briefing)
        self.assertIn('medical_arm_6dof_schema.yaml', briefing)
        self.assertIn('medical_arm_6dof_hardware_shadow.launch.py', briefing)
        self.assertIn('JointTrajectory -> NanoPi -> M33 -> 电机', briefing)
        self.assertIn('M33 -> MSG_TYPE_SENSOR_SNAPSHOT / MSG_TYPE_SENSOR_STREAM -> M55', briefing)
        self.assertIn('M33 -> CAN 0x323 -> NanoPi -> /rehab_arm/model_state', briefing)
        self.assertIn('不能说 VLA 已经能安全控制真机', briefing)
        self.assertIn('7号 EL05 不在机械臂上', briefing)

        self.assertIn('motor_id_7_in_formal_mapping: false', schema)
        self.assertIn('scope: bench_debug_and_mujoco_shadow_only', schema)
        self.assertIn('temporary_substitute_for_medical_arm_6dof_joint: jian_xuanzhuan_joint', schema)


if __name__ == '__main__':
    unittest.main()
