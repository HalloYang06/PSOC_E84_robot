import unittest

from rehab_arm_psoc_bridge.m33_gate_preparation import build_m33_gate_preparation_package
from rehab_arm_psoc_bridge.operator_review import build_operator_review_record


class TestM33GatePreparation(unittest.TestCase):
    def _review(self):
        return build_operator_review_record(
            robot_id='arm',
            device_id='nanopi',
            session_id='session_1',
            reviewer_id='operator_1',
            reviewer_role='operator',
            approved_for_m33_gate_preparation=True,
            source_plan_id='plan_1',
            mujoco_report_id='mujoco_1',
            now=100.0,
        )

    def test_ready_when_review_psoc_and_feedback_pass(self):
        package = build_m33_gate_preparation_package(
            self._review(),
            psoc_status={'motion_allowed': True, 'state': 'ok', 'control_mode': 'armed', 'error_code': 0},
            last_fresh_motor_status_age_sec=0.2,
            fresh_motor_status_count=4,
            now=101.0,
        )

        self.assertTrue(package['ready_for_m33_gate'])
        self.assertEqual(package['schema_version'], 'm33_gate_preparation_package_v1')
        self.assertIn('prepare_joint_trajectory_for_m33_gate', package['allowed_next_steps'])
        self.assertIn('send_can_frame_directly', package['forbidden_next_steps'])
        self.assertEqual(package['control_boundary'], 'm33_gate_preparation_only_not_motion_permission')

    def test_blocks_without_psoc_motion_allowed(self):
        package = build_m33_gate_preparation_package(
            self._review(),
            psoc_status={'motion_allowed': False, 'state': 'limited', 'control_mode': 'logging_only', 'error_code': 0},
            last_fresh_motor_status_age_sec=0.2,
            fresh_motor_status_count=4,
            now=101.0,
        )

        self.assertFalse(package['ready_for_m33_gate'])
        self.assertEqual(package['allowed_next_steps'], [])
        self.assertFalse(package['safety_checks']['psoc_motion_gate']['ok'])

    def test_blocks_without_fresh_feedback(self):
        package = build_m33_gate_preparation_package(
            self._review(),
            psoc_status={'motion_allowed': True, 'state': 'ok', 'control_mode': 'armed', 'error_code': 0},
            last_fresh_motor_status_age_sec=None,
            fresh_motor_status_count=0,
            now=101.0,
        )

        self.assertFalse(package['ready_for_m33_gate'])
        self.assertEqual(package['allowed_next_steps'], [])
        self.assertFalse(package['safety_checks']['fresh_motor_feedback_gate']['ok'])


if __name__ == '__main__':
    unittest.main()
