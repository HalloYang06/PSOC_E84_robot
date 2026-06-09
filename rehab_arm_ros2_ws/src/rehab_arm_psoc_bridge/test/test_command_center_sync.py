import unittest

from rehab_arm_psoc_bridge.command_center_sync import (
    build_command_center_sync_plan,
    make_command_center_context,
    make_minimal_command_center_snapshot,
    make_vla_task_request_payload,
)


class TestCommandCenterSync(unittest.TestCase):
    def test_context_carries_tenant_workspace_user_and_patient(self):
        context = make_command_center_context(
            tenant_id='tenant_a',
            workspace_id='workspace_rehab',
            user_id='doctor_1',
            role='doctor',
            device_id='nanopi-m5',
            patient_id='patient_1',
            session_id='session_1',
        )

        self.assertEqual(context['schema_version'], 'command_center_auth_context_v1')
        self.assertEqual(context['tenant_id'], 'tenant_a')
        self.assertEqual(context['workspace_id'], 'workspace_rehab')
        self.assertEqual(context['allowed_device_ids'], ['nanopi-m5'])
        self.assertEqual(context['allowed_patient_ids'], ['patient_1'])
        self.assertEqual(context['control_boundary'], 'auth_context_only_not_motion_permission')

    def test_snapshot_is_unknown_safe_dry_run(self):
        snapshot = make_minimal_command_center_snapshot('arm', 'nanopi', now=100.0)

        self.assertEqual(snapshot['schema_version'], 'command_center_snapshot_v1')
        self.assertFalse(snapshot['safety']['motion_allowed'])
        self.assertEqual(snapshot['wiring_health']['checks'][1]['channel'], 'c8t6_emg_can')
        self.assertEqual(snapshot['control_boundary'], 'telemetry_snapshot_only_not_motion_permission')

    def test_vla_request_forbids_low_level_motor_outputs(self):
        request = make_vla_task_request_payload(
            robot_id='arm',
            device_id='nanopi',
            session_id='session_1',
            language_goal='慢慢弯曲肘关节',
            profile_id='profile_1',
            now=100.0,
        )

        self.assertEqual(request['schema_version'], 'vla_task_request_v1')
        self.assertIn('dry_run_joint_trajectory_candidate', request['allowed_outputs'])
        self.assertIn('can_frame', request['forbidden_outputs'])
        self.assertIn('m33_safety_override', request['forbidden_outputs'])
        self.assertEqual(request['context_refs']['active_profile_id'], 'profile_1')

    def test_plan_builds_rest_and_websocket_without_motion_permission(self):
        plan = build_command_center_sync_plan(
            robot_id='arm',
            device_id='nanopi',
            tenant_id='tenant_a',
            workspace_id='workspace_rehab',
            user_id='operator_1',
            patient_id='patient_1',
            session_id='session_1',
            profile_id='profile_1',
            profile_version=2,
            base_url='http://server.local/api/rehab-arm/v1/',
            now=100.0,
        )

        self.assertEqual(plan['schema_version'], 'command_center_sync_plan_v1')
        self.assertEqual(plan['base_url'], 'http://server.local/api/rehab-arm/v1')
        self.assertEqual(len(plan['requests']), 5)
        self.assertEqual(plan['websocket_subscriptions'][0]['url'], 'http://server.local/api/rehab-arm/v1/devices/nanopi/events')
        self.assertEqual(plan['auth_context']['tenant_id'], 'tenant_a')
        self.assertIn('motion_allowed_override', plan['forbidden_outputs'])
        for request in plan['requests']:
            self.assertEqual(request['json']['auth_context']['workspace_id'], 'workspace_rehab')
            self.assertEqual(request['control_boundary'], 'planned_http_request_only_not_motion_permission')
            self.assertNotIn('motor_current', request['purpose'])


if __name__ == '__main__':
    unittest.main()
