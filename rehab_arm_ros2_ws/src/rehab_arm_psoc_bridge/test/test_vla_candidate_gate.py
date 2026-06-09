import copy
import unittest

from rehab_arm_psoc_bridge.vla_candidate_gate import (
    build_example_vla_plan_candidate,
    validate_vla_plan_candidate,
)


class TestVlaCandidateGate(unittest.TestCase):
    def test_accepts_builtin_dry_run_candidate(self):
        candidate = build_example_vla_plan_candidate(now=100.0)

        report = validate_vla_plan_candidate(candidate)

        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['schema_version'], 'vla_candidate_gate_report_v1')
        self.assertIn('mujoco_dry_run_review', report['allowed_next_steps'])
        self.assertIn('publish_joint_trajectory', report['forbidden_next_steps'])
        self.assertEqual(report['control_boundary'], 'vla_candidate_gate_only_not_motion_permission')

    def test_rejects_low_level_motor_fields(self):
        candidate = build_example_vla_plan_candidate(now=100.0)
        candidate['candidate']['points'][0]['motor_current'] = 0.2

        report = validate_vla_plan_candidate(candidate)

        self.assertFalse(report['ok'])
        self.assertIn('forbidden low-level control fields', report['errors'][0])
        self.assertEqual(report['allowed_next_steps'], [])

    def test_rejects_unknown_joint_and_shape_mismatch(self):
        candidate = build_example_vla_plan_candidate(now=100.0)
        candidate['candidate']['joint_names'] = ['unknown_joint', 'zhou_zongxiang_joint']
        candidate['candidate']['points'][0]['positions'] = [0.1]

        report = validate_vla_plan_candidate(candidate)

        self.assertFalse(report['ok'])
        self.assertIn("candidate.joint_names contains unknown joint 'unknown_joint'", report['errors'])
        self.assertIn('candidate.points[0].positions length must match candidate.joint_names length', report['errors'])

    def test_rejects_missing_required_reviews(self):
        candidate = build_example_vla_plan_candidate(now=100.0)
        candidate['requires'] = ['human_confirmation']

        report = validate_vla_plan_candidate(candidate)

        self.assertFalse(report['ok'])
        self.assertIn('requires must include mujoco_dry_run_passed', report['errors'])
        self.assertIn('requires must include m33_motion_allowed_true', report['errors'])

    def test_rejects_non_monotonic_timestamps(self):
        candidate = build_example_vla_plan_candidate(now=100.0)
        second = copy.deepcopy(candidate['candidate']['points'][0])
        second['time_from_start_sec'] = 1.0
        candidate['candidate']['points'].append(second)

        report = validate_vla_plan_candidate(candidate)

        self.assertFalse(report['ok'])
        self.assertIn('candidate.points[1].time_from_start_sec must be strictly increasing', report['errors'])


if __name__ == '__main__':
    unittest.main()
