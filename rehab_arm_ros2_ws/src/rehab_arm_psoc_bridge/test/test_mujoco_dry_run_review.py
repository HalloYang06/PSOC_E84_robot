import copy
import unittest

from rehab_arm_psoc_bridge.mujoco_dry_run_review import (
    build_mujoco_dry_run_review_plan,
    validate_mujoco_dry_run_review_report,
)
from rehab_arm_psoc_bridge.vla_candidate_gate import build_example_vla_plan_candidate


class TestMujocoDryRunReview(unittest.TestCase):
    def test_builds_review_plan_from_safe_candidate(self):
        candidate = build_example_vla_plan_candidate(now=100.0)

        plan = build_mujoco_dry_run_review_plan(
            candidate,
            robot_id='arm',
            device_id='nanopi',
            session_id='session_1',
            now=101.0,
        )

        self.assertEqual(plan['schema_version'], 'mujoco_dry_run_review_plan_v1')
        self.assertTrue(plan['accepted_for_review'])
        self.assertEqual(plan['sim_target']['sim_model'], 'medical_arm_6dof.xml')
        self.assertEqual(plan['sim_target']['command_topic'], '/sim/medical_arm/trajectory_candidate')
        self.assertIn('run_mujoco_dry_run', plan['allowed_next_steps'])
        self.assertIn('publish_joint_trajectory', plan['forbidden_next_steps'])
        self.assertEqual(plan['control_boundary'], 'mujoco_dry_run_plan_only_not_motion_permission')

    def test_blocks_review_plan_when_candidate_gate_fails(self):
        candidate = build_example_vla_plan_candidate(now=100.0)
        candidate['candidate']['points'][0]['can_frame'] = '320#0102'

        plan = build_mujoco_dry_run_review_plan(
            candidate,
            robot_id='arm',
            device_id='nanopi',
            session_id='session_1',
            now=101.0,
        )

        self.assertFalse(plan['accepted_for_review'])
        self.assertEqual(plan['blocked_reason'], 'vla_candidate_gate_failed')
        self.assertFalse(plan['gate_report']['ok'])
        self.assertEqual(plan['allowed_next_steps'], [])

    def test_accepts_safe_mujoco_review_report(self):
        report = {
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

        quality = validate_mujoco_dry_run_review_report(report)

        self.assertTrue(quality['ok'], quality['errors'])
        self.assertIn('operator_review', quality['allowed_next_steps'])
        self.assertIn('send_can_frame', quality['forbidden_next_steps'])

    def test_rejects_mujoco_report_that_grants_motion(self):
        report = {
            'schema_version': 'mujoco_dry_run_review_report_v1',
            'dry_run_passed': True,
            'motion_permission_granted': True,
            'checks': [{'name': 'load_mjcf_model', 'passed': True}],
            'control_boundary': 'mujoco_review_only_not_motion_permission',
        }

        quality = validate_mujoco_dry_run_review_report(report)

        self.assertFalse(quality['ok'])
        self.assertIn('MuJoCo dry-run report must not grant real motion permission', quality['errors'])

    def test_rejects_failed_review_check(self):
        report = {
            'schema_version': 'mujoco_dry_run_review_report_v1',
            'dry_run_passed': True,
            'motion_permission_granted': False,
            'checks': [{'name': 'limit_check', 'passed': False}],
            'control_boundary': 'mujoco_review_only_not_motion_permission',
        }

        quality = validate_mujoco_dry_run_review_report(copy.deepcopy(report))

        self.assertFalse(quality['ok'])
        self.assertIn('checks[0] limit_check must pass', quality['errors'])


if __name__ == '__main__':
    unittest.main()
