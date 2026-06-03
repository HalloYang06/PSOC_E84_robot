from __future__ import annotations

import unittest
from pathlib import Path

import yaml


SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / 'config'
    / 'medical_arm_6dof_schema.yaml'
)


class MedicalArm6DofSchemaTests(unittest.TestCase):
    def test_schema_records_six_urdf_joints(self) -> None:
        payload = yaml.safe_load(SCHEMA_PATH.read_text(encoding='utf-8'))

        joints = payload['joints']
        self.assertEqual(
            [joint['urdf_joint'] for joint in joints],
            [
                'jian_hengxiang_joint',
                'jian_zongxiang_joint',
                'jian_xuanzhuan_joint',
                'zhou_zongxiang_joint',
                'wanbu_zongxiang_joint',
                'wanbu_hengxiang_joint',
            ],
        )
        self.assertEqual([joint['index'] for joint in joints], list(range(6)))

    def test_schema_keeps_hardware_authority_disabled_by_default(self) -> None:
        payload = yaml.safe_load(SCHEMA_PATH.read_text(encoding='utf-8'))

        self.assertFalse(payload['safety']['default_enable_target_tx'])
        self.assertFalse(payload['safety']['allow_direct_motor_command'])
        self.assertFalse(payload['safety']['allow_vla_can_output'])
        self.assertFalse(payload['safety']['motor_id_7_in_formal_mapping'])
        self.assertTrue(payload['safety']['allow_motor_id_7_as_temporary_mujoco_shadow_actuator'])

    def test_known_motor_mapping_matches_current_draft(self) -> None:
        payload = yaml.safe_load(SCHEMA_PATH.read_text(encoding='utf-8'))
        mapping = {
            joint['urdf_joint']: joint['motor_ref']
            for joint in payload['joints']
        }

        self.assertEqual(mapping['jian_hengxiang_joint']['kind'], 'node_id')
        self.assertEqual(mapping['jian_hengxiang_joint']['id'], 3)
        self.assertEqual(
            mapping['jian_hengxiang_joint']['transmission']['motor_to_joint_ratio'],
            0.5,
        )
        self.assertEqual(mapping['jian_zongxiang_joint']['id'], 4)
        self.assertEqual(mapping['jian_xuanzhuan_joint']['id'], 6)
        self.assertEqual(mapping['zhou_zongxiang_joint']['id'], 5)
        self.assertEqual(mapping['wanbu_zongxiang_joint']['candidates'], [1, 2])
        self.assertEqual(mapping['wanbu_hengxiang_joint']['candidates'], [1, 2])

    def test_motor_7_is_external_debug_only(self) -> None:
        payload = yaml.safe_load(SCHEMA_PATH.read_text(encoding='utf-8'))

        external_motor = payload['external_debug_motors'][0]
        self.assertEqual(external_motor['motor_id'], 7)
        self.assertEqual(external_motor['status'], 'external_debug_only_not_mounted_on_arm')
        self.assertEqual(external_motor['model'], 'EL05')
        self.assertEqual(external_motor['joint_command_ratio'], 1.0)
        self.assertEqual(external_motor['drive_internal_reduction_ratio'], 9.0)
        self.assertFalse(external_motor['allowed_in_formal_mapping'])
        self.assertTrue(external_motor['allowed_as_temporary_mujoco_shadow_actuator'])
        self.assertEqual(external_motor['temporary_shadow_joint'], 'forearm_rotation_joint')


if __name__ == '__main__':
    unittest.main()
