import unittest

from rehab_arm_psoc_bridge.voice_gateway import (
    build_voice_pipeline_plan,
    make_tts_playback_request,
    make_voice_capture_payload,
    make_voice_relay_payload,
)


class TestVoiceGateway(unittest.TestCase):
    def test_voice_capture_is_input_only(self):
        payload = make_voice_capture_payload(
            robot_id='arm',
            device_id='nanopi',
            transcript='开始训练',
            wake_detected=True,
            confidence=1.5,
            now=100.0,
        )

        self.assertEqual(payload['schema_version'], 'voice_capture_v1')
        self.assertEqual(payload['confidence'], 1.0)
        self.assertEqual(payload['control_boundary'], 'voice_input_only_not_motion_permission')

    def test_voice_relay_maps_to_model_state(self):
        capture = make_voice_capture_payload('arm', 'nanopi', now=100.0)
        payload = make_voice_relay_payload(
            capture,
            result_label='voice_pain_or_discomfort',
            transcript='有点疼',
            confidence=0.87,
            now=101.0,
        )

        result = payload['as_model_state']['model_results'][0]
        self.assertEqual(payload['schema_version'], 'voice_relay_v1')
        self.assertEqual(result['model_id'], 'm55_voice_asr_v1')
        self.assertEqual(result['result_code'], 4)
        self.assertEqual(payload['control_boundary'], 'voice_relay_only_not_motion_permission')
        self.assertEqual(payload['as_model_state']['control_boundary'], 'model_suggestion_only_not_motion_permission')

    def test_tts_request_is_feedback_only(self):
        payload = make_tts_playback_request('arm', 'nanopi', '收到', now=100.0)

        self.assertEqual(payload['schema_version'], 'tts_playback_request_v1')
        self.assertEqual(payload['target'], 'm55_speaker')
        self.assertEqual(payload['control_boundary'], 'tts_feedback_only_not_motion_permission')

    def test_pipeline_plan_contains_no_motion_outputs(self):
        plan = build_voice_pipeline_plan('arm', 'nanopi', now=100.0)

        self.assertEqual(plan['schema_version'], 'rehab_arm_voice_pipeline_plan_v1')
        self.assertIn('can_frame', plan['forbidden_outputs'])
        self.assertEqual(plan['control_boundary'], 'voice_pipeline_plan_only_not_motion_permission')


if __name__ == '__main__':
    unittest.main()
