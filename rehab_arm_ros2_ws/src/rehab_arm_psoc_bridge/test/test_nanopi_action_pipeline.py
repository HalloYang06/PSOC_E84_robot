import unittest

from rehab_arm_psoc_bridge.nanopi_action_pipeline import (
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


if __name__ == '__main__':
    unittest.main()
