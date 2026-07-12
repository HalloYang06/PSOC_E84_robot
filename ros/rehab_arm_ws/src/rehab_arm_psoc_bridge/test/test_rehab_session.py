import unittest

from rehab_arm_psoc_bridge.rehab_session import build_rehab_session_plan


class TestRehabSession(unittest.TestCase):
    def test_plan_reserves_emg_and_path_planning_boundaries(self):
        plan = build_rehab_session_plan(
            robot_id='arm',
            device_id='nanopi',
            training_mode='active_assist',
            now=100.0,
        )

        self.assertEqual(plan['schema_version'], 'rehab_session_plan_v1')
        self.assertEqual(plan['emg_input_contract']['channel_count'], 4)
        self.assertIn('/rehab_arm/model_state', plan['required_topics'])
        self.assertIn('dry_run_joint_trajectory_candidate', plan['path_planning_contract']['output'])
        self.assertIn('can_frame', plan['path_planning_contract']['forbidden_outputs'])
        self.assertEqual(plan['control_boundary'], 'rehab_session_plan_only_not_motion_permission')

    def test_rejects_unknown_mode(self):
        with self.assertRaises(ValueError):
            build_rehab_session_plan('arm', 'nanopi', 'unsafe_free_drive')


if __name__ == '__main__':
    unittest.main()
