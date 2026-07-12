import unittest

from rehab_arm_psoc_bridge.m33_model_status import (
    M33_MODEL_STATUS_FLAG_DETECTED,
    M33_MODEL_STATUS_FLAG_FRESH,
    M33_MODEL_STATUS_FLAG_SUGGESTION_ONLY,
    M33_MODEL_STATUS_ID,
    parse_m33_model_status_frame,
)


class TestM33ModelStatus(unittest.TestCase):
    def test_parse_wake_word_status(self):
        flags = (
            M33_MODEL_STATUS_FLAG_FRESH
            | M33_MODEL_STATUS_FLAG_DETECTED
            | M33_MODEL_STATUS_FLAG_SUGGESTION_ONLY
        )
        payload = parse_m33_model_status_frame(
            M33_MODEL_STATUS_ID,
            bytes([0xB5, 0x12, 0x01, 0x01, 87, flags, 32, 0]),
        )

        self.assertTrue(payload['valid'])
        self.assertEqual(payload['model_name'], 'm55_wake_word_v1')
        self.assertEqual(payload['result_name'], 'wake_start_request')
        self.assertAlmostEqual(payload['confidence'], 0.87)
        self.assertTrue(payload['fresh'])
        self.assertTrue(payload['detected'])
        self.assertTrue(payload['suggestion_only'])
        self.assertEqual(payload['window_ms'], 320)
        self.assertEqual(payload['control_boundary'], 'model_suggestion_only_not_motion_permission')

    def test_rejects_bad_marker(self):
        payload = parse_m33_model_status_frame(
            M33_MODEL_STATUS_ID,
            bytes([0x00, 0x12, 0x01, 0x01, 87, 0x80, 32, 0]),
        )

        self.assertFalse(payload['valid'])
        self.assertEqual(payload['detail'], 'bad_marker')

    def test_parse_voice_asr_status(self):
        payload = parse_m33_model_status_frame(
            M33_MODEL_STATUS_ID,
            bytes([0xB5, 0x13, 0x04, 0x04, 91, 0x83, 20, 0]),
        )

        self.assertTrue(payload['valid'])
        self.assertEqual(payload['model_name'], 'm55_voice_asr_v1')
        self.assertEqual(payload['result_name'], 'voice_pain_or_discomfort')
        self.assertEqual(payload['control_boundary'], 'model_suggestion_only_not_motion_permission')


if __name__ == '__main__':
    unittest.main()
