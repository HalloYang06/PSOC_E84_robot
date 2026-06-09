import unittest

from rehab_arm_psoc_bridge.operator_review import (
    build_operator_review_record,
    validate_operator_review_record,
)


class TestOperatorReview(unittest.TestCase):
    def test_accepts_approved_review_for_m33_gate_preparation_only(self):
        record = build_operator_review_record(
            robot_id='arm',
            device_id='nanopi',
            session_id='session_1',
            reviewer_id='operator_1',
            reviewer_role='operator',
            patient_id='patient_1',
            profile_id='profile_1',
            approved_for_m33_gate_preparation=True,
            now=100.0,
        )

        report = validate_operator_review_record(record)

        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['schema_version'], 'operator_review_quality_report_v1')
        self.assertIn('prepare_joint_trajectory_for_m33_gate', report['allowed_next_steps'])
        self.assertIn('send_can_frame', report['forbidden_next_steps'])
        self.assertEqual(report['control_boundary'], 'operator_review_quality_gate_only_not_motion_permission')

    def test_rejects_missing_reviewer_identity(self):
        record = build_operator_review_record(
            robot_id='arm',
            device_id='nanopi',
            session_id='session_1',
            reviewer_id='operator_1',
            reviewer_role='operator',
            approved_for_m33_gate_preparation=False,
            now=100.0,
        )
        record['reviewer'].pop('user_id')

        report = validate_operator_review_record(record)

        self.assertFalse(report['ok'])
        self.assertIn('reviewer.user_id is required', report['errors'])

    def test_rejects_unknown_role(self):
        record = build_operator_review_record(
            robot_id='arm',
            device_id='nanopi',
            session_id='session_1',
            reviewer_id='user_1',
            reviewer_role='viewer',
            approved_for_m33_gate_preparation=False,
            now=100.0,
        )

        report = validate_operator_review_record(record)

        self.assertFalse(report['ok'])
        self.assertTrue(any(error.startswith('reviewer.role must be one of') for error in report['errors']))

    def test_rejects_missing_acknowledgement(self):
        record = build_operator_review_record(
            robot_id='arm',
            device_id='nanopi',
            session_id='session_1',
            reviewer_id='operator_1',
            reviewer_role='operator',
            approved_for_m33_gate_preparation=True,
            now=100.0,
        )
        record['required_acknowledgements'].remove('estop_available')

        report = validate_operator_review_record(record)

        self.assertFalse(report['ok'])
        self.assertIn('required_acknowledgements must include estop_available', report['errors'])

    def test_rejects_missing_forbidden_step(self):
        record = build_operator_review_record(
            robot_id='arm',
            device_id='nanopi',
            session_id='session_1',
            reviewer_id='operator_1',
            reviewer_role='operator',
            approved_for_m33_gate_preparation=True,
            now=100.0,
        )
        record['forbidden_next_steps'].remove('override_m33_safety')

        report = validate_operator_review_record(record)

        self.assertFalse(report['ok'])
        self.assertIn('forbidden_next_steps must include override_m33_safety', report['errors'])


if __name__ == '__main__':
    unittest.main()
