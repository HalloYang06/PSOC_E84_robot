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

    def test_command_center_and_app_protocol_preserves_safety_boundary(self) -> None:
        protocol = (
            REPO_ROOT
            / 'docs'
            / 'COMMAND_CENTER_APP_PROTOCOL_V1.md'
        ).read_text(encoding='utf-8')
        integration = (
            REPO_ROOT
            / 'docs'
            / 'INTEGRATION_GUIDE.md'
        ).read_text(encoding='utf-8')
        briefing = (
            REPO_ROOT
            / 'docs'
            / 'CURRENT_PROJECT_BRIEFING.md'
        ).read_text(encoding='utf-8')

        self.assertIn('JointTrajectory -> NanoPi -> M33 -> motor', protocol)
        self.assertIn('Three.js + URDF', protocol)
        self.assertIn('camera_keyframe_v1', protocol)
        self.assertIn('voice_relay_v1', protocol)
        self.assertIn('vla_plan_candidate_v1', protocol)
        self.assertIn('wiring_health_v1', protocol)
        self.assertIn('safety_state_v1', protocol)
        self.assertIn('estop_request_v1', protocol)
        self.assertIn('estop_ack_v1', protocol)
        self.assertIn('not_safe_until_m33_ack', protocol)
        self.assertIn('App 禁止', protocol)
        self.assertIn('服务器不得直接发 CAN', protocol)
        self.assertIn('COMMAND_CENTER_APP_PROTOCOL_V1.md', integration)
        self.assertIn('COMMAND_CENTER_APP_PROTOCOL_V1.md', briefing)

    def test_command_center_requires_tenant_isolation(self) -> None:
        protocol = (
            REPO_ROOT
            / 'docs'
            / 'COMMAND_CENTER_APP_PROTOCOL_V1.md'
        ).read_text(encoding='utf-8')
        roadmap = (
            REPO_ROOT
            / 'docs'
            / 'REHAB_FUNCTIONAL_ROADMAP.md'
        ).read_text(encoding='utf-8')
        lessons = (
            REPO_ROOT
            / 'docs'
            / 'TROUBLESHOOTING_AND_LESSONS.md'
        ).read_text(encoding='utf-8')

        for field in (
            'tenant_id',
            'workspace_id',
            'user_id',
            'role',
            'device_id',
            'patient_id',
        ):
            self.assertIn(field, protocol)
            self.assertIn(field, roadmap)

        self.assertIn('WebSocket 事件只能推送给有该 `device_id` 权限的连接', protocol)
        self.assertIn('不同账号、不同团队、不同患者的数据默认不可见', roadmap)
        self.assertIn('不要把 qiansai 当成云端 AI 合作平台', lessons)

    def test_voice_and_rehab_session_contracts_are_dry_run_only(self) -> None:
        voice_guide = (
            REPO_ROOT
            / 'docs'
            / 'VOICE_WAKE_TTS_PORTABILITY_GUIDE.md'
        ).read_text(encoding='utf-8')
        roadmap = (
            REPO_ROOT
            / 'docs'
            / 'REHAB_FUNCTIONAL_ROADMAP.md'
        ).read_text(encoding='utf-8')
        setup = (
            REPO_ROOT
            / 'rehab_arm_ros2_ws'
            / 'src'
            / 'rehab_arm_psoc_bridge'
            / 'setup.py'
        ).read_text(encoding='utf-8')
        cmake = (
            REPO_ROOT
            / 'rehab_arm_ros2_ws'
            / 'src'
            / 'rehab_arm_psoc_bridge'
            / 'CMakeLists.txt'
        ).read_text(encoding='utf-8')

        self.assertIn('micro_speech', voice_guide)
        self.assertIn('micro-wake-word', voice_guide)
        self.assertIn('M33 m55_model_bridge', voice_guide)
        self.assertIn('CAN 0x323', voice_guide)
        self.assertIn('不能输出 `0x320`', voice_guide)
        self.assertIn('emg_feature_window_v1', roadmap)
        self.assertIn('dry_run_joint_trajectory_candidate', roadmap)
        self.assertIn('build_voice_pipeline_plan', setup)
        self.assertIn('build_rehab_session_plan', setup)
        self.assertIn('build_voice_pipeline_plan.py', cmake)
        self.assertIn('build_rehab_session_plan.py', cmake)


if __name__ == '__main__':
    unittest.main()
