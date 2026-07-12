import copy
import unittest

from rehab_arm_psoc_bridge.server_action_ingress import (
    build_example_server_action_command,
    make_nanopi_action_queue_item,
    validate_server_action_command,
)


class TestServerActionIngress(unittest.TestCase):
    def test_accepts_high_level_action_only(self):
        payload = build_example_server_action_command(now=100.0)

        report = validate_server_action_command(payload)

        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['schema_version'], 'server_action_ingress_gate_report_v1')
        self.assertIn('mujoco_dry_run_review', report['allowed_next_steps'])
        self.assertIn('send_can_frame', report['forbidden_next_steps'])
        self.assertEqual(report['control_boundary'], 'server_action_ingress_gate_only_not_motion_permission')

    def test_rejects_low_level_fields(self):
        payload = build_example_server_action_command(now=100.0)
        payload['action']['motor_current'] = 0.2

        report = validate_server_action_command(payload)

        self.assertFalse(report['ok'])
        self.assertIn('forbidden low-level control fields', report['errors'][0])
        self.assertEqual(report['allowed_next_steps'], [])

    def test_rejects_missing_required_safety_steps(self):
        payload = build_example_server_action_command(now=100.0)
        payload['requires_before_motion'] = ['operator_confirmation_required']

        report = validate_server_action_command(payload)

        self.assertFalse(report['ok'])
        self.assertIn('requires_before_motion must include mujoco_dry_run_required', report['errors'])
        self.assertIn('requires_before_motion must include m33_final_gate_required', report['errors'])

    def test_rejects_direct_publish_next_step(self):
        payload = build_example_server_action_command(now=100.0)
        payload['allowed_next_steps'].append('publish_joint_trajectory')

        report = validate_server_action_command(payload)

        self.assertFalse(report['ok'])
        self.assertIn('allowed_next_steps must not include publish_joint_trajectory', report['errors'])

    def test_warns_when_vision_context_missing(self):
        payload = build_example_server_action_command(now=100.0)
        payload = copy.deepcopy(payload)
        payload['source_refs'].pop('vla_vision_context_id')

        report = validate_server_action_command(payload)

        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['warning_count'], 1)

    def test_accepts_into_nanopi_high_level_queue_only(self):
        payload = build_example_server_action_command(now=100.0)
        report = validate_server_action_command(payload)

        queue_item = make_nanopi_action_queue_item(payload, report, now=101.0)

        self.assertTrue(queue_item['accepted'])
        self.assertEqual(queue_item['schema_version'], 'nanopi_high_level_action_queue_item_v1')
        self.assertIn('mujoco_dry_run_review', queue_item['next_pipeline'])
        self.assertIn('send_can_frame', queue_item['blocked_pipeline'])
        self.assertEqual(queue_item['control_boundary'], 'nanopi_action_queue_only_not_motion_permission')


if __name__ == '__main__':
    unittest.main()
