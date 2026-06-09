import unittest

from rehab_arm_psoc_bridge.nanopi_action_pipeline import (
    build_operator_review_request_from_dry_run,
    build_nanopi_action_pipeline_plan,
    build_pipeline_from_server_action,
)
from rehab_arm_psoc_bridge.server_action_ingress import (
    build_example_server_action_command,
    make_nanopi_action_queue_item,
)


class TestNanoPiActionPipeline(unittest.TestCase):
    def test_builds_pipeline_from_server_action_to_mujoco_review(self):
        server_action = build_example_server_action_command(now=100.0)

        plan = build_pipeline_from_server_action(server_action, session_id='session_1', now=101.0)

        self.assertTrue(plan['accepted_for_pipeline'])
        self.assertEqual(plan['schema_version'], 'nanopi_action_pipeline_plan_v1')
        self.assertEqual(plan['candidate']['candidate']['type'], 'dry_run_joint_trajectory')
        self.assertEqual(plan['dry_run_review_plan']['schema_version'], 'mujoco_dry_run_review_plan_v1')
        self.assertTrue(plan['dry_run_review_plan']['accepted_for_review'])
        self.assertIn('send_can_frame', plan['forbidden_next_steps'])
        self.assertEqual(plan['control_boundary'], 'nanopi_action_pipeline_plan_only_not_motion_permission')

    def test_blocks_rejected_queue_item(self):
        server_action = build_example_server_action_command(now=100.0)
        server_action['action']['motor_current'] = 1.0
        queue_item = make_nanopi_action_queue_item(server_action, now=101.0)

        plan = build_nanopi_action_pipeline_plan(queue_item, session_id='session_1', now=102.0)

        self.assertFalse(plan['accepted_for_pipeline'])
        self.assertEqual(plan['blocked_reason'], 'queue_item_not_accepted')
        self.assertEqual(plan['allowed_next_steps'], [])

    def test_dry_run_report_can_prepare_operator_review_request(self):
        server_action = build_example_server_action_command(now=100.0)
        plan = build_pipeline_from_server_action(server_action, session_id='session_1', now=101.0)
        dry_run_report = {
            'schema_version': 'mujoco_dry_run_review_report_v1',
            'dry_run_passed': True,
            'motion_permission_granted': False,
            'checks': [
                {'name': 'load_mjcf_model', 'passed': True},
                {'name': 'limit_check', 'passed': True},
                {'name': 'continuity_check', 'passed': True},
            ],
            'control_boundary': 'mujoco_review_only_not_motion_permission',
        }

        request = build_operator_review_request_from_dry_run(plan, dry_run_report, now=102.0)

        self.assertTrue(request['ready_for_operator_review'])
        self.assertEqual(request['schema_version'], 'operator_review_request_v1')
        self.assertIn('build_operator_review_record', request['allowed_next_steps'])
        self.assertIn('send_can_frame', request['forbidden_next_steps'])
        self.assertEqual(request['control_boundary'], 'operator_review_request_only_not_motion_permission')

    def test_failed_dry_run_report_blocks_operator_review(self):
        server_action = build_example_server_action_command(now=100.0)
        plan = build_pipeline_from_server_action(server_action, session_id='session_1', now=101.0)
        dry_run_report = {
            'schema_version': 'mujoco_dry_run_review_report_v1',
            'dry_run_passed': False,
            'motion_permission_granted': False,
            'checks': [{'name': 'limit_check', 'passed': False}],
            'control_boundary': 'mujoco_review_only_not_motion_permission',
        }

        request = build_operator_review_request_from_dry_run(plan, dry_run_report, now=102.0)

        self.assertFalse(request['ready_for_operator_review'])
        self.assertEqual(request['allowed_next_steps'], [])


if __name__ == '__main__':
    unittest.main()
