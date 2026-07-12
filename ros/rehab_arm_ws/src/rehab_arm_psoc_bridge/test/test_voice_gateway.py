import unittest

from rehab_arm_psoc_bridge.voice_gateway import (
    build_voice_pipeline_plan,
    classify_voice_utterance,
    make_m55_http_voice_relay_request,
    make_tts_playback_request,
    make_vla_language_context_payload,
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
        self.assertEqual(payload['vla_language_context']['source'], 'm55_http_voice_to_server_language_relay')

    def test_classifies_daily_chat_without_vla_action(self):
        classification = classify_voice_utterance('你好，今天可以陪我聊聊天吗')

        self.assertEqual(classification['kind'], 'daily_chat')
        self.assertEqual(classification['route'], 'conversation_reply')
        self.assertFalse(classification['requires_vla_action'])

    def test_classifies_rehab_command_as_vla_l(self):
        capture = make_voice_capture_payload('arm', 'nanopi', now=100.0)
        payload = make_vla_language_context_payload(
            capture,
            transcript='开始抬手训练',
            confidence=0.91,
            now=101.0,
        )

        self.assertEqual(payload['schema_version'], 'vla_language_context_v1')
        self.assertEqual(payload['utterance_classification']['kind'], 'vla_command')
        self.assertEqual(payload['allowed_next_step'], 'server_vla_l_context_over_http')
        self.assertEqual(payload['control_boundary'], 'vla_language_only_not_motion_permission')
        self.assertIn('direct_motor_command', payload['forbidden_outputs'])

    def test_m55_http_voice_relay_request_is_not_can(self):
        capture = make_voice_capture_payload(
            'rehab-arm-alpha',
            'nanopi-m5',
            transcript='你好',
            wake_detected=True,
            now=100.0,
        )
        request = make_m55_http_voice_relay_request(capture, transcript='你好')

        self.assertEqual(request['schema_version'], 'm55_http_voice_relay_request_v1')
        self.assertEqual(request['method'], 'POST')
        self.assertIn('/model/relay', request['url'])
        self.assertEqual(request['transport_boundary'], 'm55_wifi_http_not_can')
        self.assertEqual(request['body_json']['input_type'], 'vla_language_from_voice')
        self.assertIn('utterance_classification', request['body_json']['requested_outputs'])
        self.assertIn('can_frame', request['body_json']['forbidden_outputs'])

    def test_tts_request_is_feedback_only(self):
        payload = make_tts_playback_request('arm', 'nanopi', '收到', now=100.0)

        self.assertEqual(payload['schema_version'], 'tts_playback_request_v1')
        self.assertEqual(payload['target'], 'm55_speaker')
        self.assertEqual(payload['control_boundary'], 'tts_feedback_only_not_motion_permission')

    def test_pipeline_plan_contains_no_motion_outputs(self):
        plan = build_voice_pipeline_plan('arm', 'nanopi', now=100.0)

        self.assertEqual(plan['schema_version'], 'rehab_arm_voice_pipeline_plan_v1')
        self.assertEqual(plan['wake_model_policy'], 'infineon_local_voice_first_then_tflm_or_micro_wake_word')
        self.assertEqual(
            plan['official_reference']['repo'],
            'https://github.com/Infineon/mtb-example-psoc-edge-mains-powered-local-voice',
        )
        self.assertIn(
            'do not revive the old custom wake route as the main path; keep it as diagnostics only',
            plan['portability_rules'],
        )
        self.assertIn('can_frame', plan['forbidden_outputs'])
        self.assertEqual(plan['utterance_routing']['cloud_voice_transport'], 'm55_wifi_http_not_can')
        self.assertEqual(plan['control_boundary'], 'voice_pipeline_plan_only_not_motion_permission')


if __name__ == '__main__':
    unittest.main()
