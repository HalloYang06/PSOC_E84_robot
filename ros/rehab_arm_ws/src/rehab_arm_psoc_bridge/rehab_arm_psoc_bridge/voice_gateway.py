from __future__ import annotations

import time
from hashlib import sha256


VOICE_CAPTURE_SCHEMA_VERSION = 'voice_capture_v1'
VOICE_RELAY_SCHEMA_VERSION = 'voice_relay_v1'
VLA_LANGUAGE_CONTEXT_SCHEMA_VERSION = 'vla_language_context_v1'
TTS_REQUEST_SCHEMA_VERSION = 'tts_playback_request_v1'
VOICE_PIPELINE_PLAN_SCHEMA_VERSION = 'rehab_arm_voice_pipeline_plan_v1'

DEFAULT_WAKE_PHRASE = 'xiao_yi_xiao_yi'
DEFAULT_AUDIO_FORMAT = 'pcm_s16le'
DEFAULT_SAMPLE_RATE_HZ = 16000
DEFAULT_CHANNELS = 1
DEFAULT_WAKE_MODEL_POLICY = 'infineon_local_voice_first_then_tflm_or_micro_wake_word'
INFINEON_LOCAL_VOICE_EXAMPLE = 'Infineon PSOC Edge mains-powered local voice'
DEFAULT_PROJECT_ID = 'fd6a55ed-a63c-44b3-b123-96fb3c154966'
DEFAULT_RELAY_BASE_URL = 'http://106.55.62.122:8011'

CHAT_KEYWORDS = (
    '你好',
    '在吗',
    '聊天',
    '讲个',
    '天气',
    '谢谢',
    '你是谁',
    '陪我',
)
COMMAND_KEYWORDS = (
    '开始',
    '训练',
    '暂停',
    '停止',
    '停下',
    '急停',
    '慢一点',
    '快一点',
    '抬手',
    '抬高',
    '放下',
    '肘',
    '肩',
    '腕',
    '疼',
    '痛',
    '不舒服',
)
COMMAND_LABELS = {
    '开始': 'voice_start_request',
    '训练': 'voice_start_request',
    '暂停': 'voice_pause_request',
    '停止': 'voice_stop_request',
    '停下': 'voice_stop_request',
    '急停': 'voice_stop_request',
    '疼': 'voice_pain_or_discomfort',
    '痛': 'voice_pain_or_discomfort',
    '不舒服': 'voice_pain_or_discomfort',
}


def stable_capture_id(
    robot_id: str,
    device_id: str,
    seq: int | None = None,
    now: float | None = None,
) -> str:
    ts = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(time.time() if now is None else now))
    parts = [robot_id.strip() or 'robot', device_id.strip() or 'device', ts]
    if seq is not None:
        parts.append(str(seq))
    raw = ':'.join(parts)
    suffix = sha256(raw.encode('utf-8')).hexdigest()[:8]
    return '__'.join(part.replace('/', '_').replace(' ', '_') for part in parts) + f'__{suffix}'


def make_voice_capture_payload(
    robot_id: str,
    device_id: str,
    source: str = 'm55_microphone',
    capture_id: str | None = None,
    audio_ref: str | None = None,
    transcript: str | None = None,
    wake_phrase: str = DEFAULT_WAKE_PHRASE,
    wake_detected: bool = False,
    confidence: float | None = None,
    sample_rate_hz: int = DEFAULT_SAMPLE_RATE_HZ,
    channels: int = DEFAULT_CHANNELS,
    audio_format: str = DEFAULT_AUDIO_FORMAT,
    duration_ms: int | None = None,
    seq: int | None = None,
    now: float | None = None,
) -> dict[str, object]:
    timestamp = time.time() if now is None else now
    payload: dict[str, object] = {
        'schema_version': VOICE_CAPTURE_SCHEMA_VERSION,
        'ts_unix': timestamp,
        'robot_id': robot_id,
        'device_id': device_id,
        'source': source,
        'capture_id': capture_id or stable_capture_id(robot_id, device_id, seq, timestamp),
        'audio_format': audio_format,
        'sample_rate_hz': int(sample_rate_hz),
        'channels': int(channels),
        'wake_phrase': wake_phrase,
        'wake_detected': bool(wake_detected),
        'control_boundary': 'voice_input_only_not_motion_permission',
    }
    if audio_ref:
        payload['audio_ref'] = audio_ref
    if transcript:
        payload['transcript'] = transcript
    if confidence is not None:
        payload['confidence'] = max(0.0, min(1.0, float(confidence)))
    if duration_ms is not None:
        payload['duration_ms'] = int(duration_ms)
    if seq is not None:
        payload['seq'] = int(seq)
    return payload


def classify_voice_utterance(transcript: str) -> dict[str, object]:
    text = (transcript or '').strip()
    lowered = text.lower()
    command_hits = [word for word in COMMAND_KEYWORDS if word in text]
    chat_hits = [word for word in CHAT_KEYWORDS if word in text]
    if command_hits:
        label = next((COMMAND_LABELS[word] for word in command_hits if word in COMMAND_LABELS), 'voice_rehab_task_request')
        return {
            'kind': 'vla_command',
            'label': label,
            'route': 'vla_language_context',
            'requires_vla_action': True,
            'reason': 'matched_rehab_command_keyword',
            'matched_keywords': command_hits,
            'control_boundary': 'classification_only_not_motion_permission',
        }
    if chat_hits or lowered:
        return {
            'kind': 'daily_chat',
            'label': 'voice_daily_chat',
            'route': 'conversation_reply',
            'requires_vla_action': False,
            'reason': 'no_rehab_command_keyword',
            'matched_keywords': chat_hits,
            'control_boundary': 'classification_only_not_motion_permission',
        }
    return {
        'kind': 'none',
        'label': 'voice_none',
        'route': 'ignore_or_prompt_again',
        'requires_vla_action': False,
        'reason': 'empty_transcript',
        'matched_keywords': [],
        'control_boundary': 'classification_only_not_motion_permission',
    }


def make_vla_language_context_payload(
    capture: dict[str, object],
    transcript: str,
    confidence: float = 0.0,
    now: float | None = None,
) -> dict[str, object]:
    classification = classify_voice_utterance(transcript)
    return {
        'schema_version': VLA_LANGUAGE_CONTEXT_SCHEMA_VERSION,
        'ts_unix': time.time() if now is None else now,
        'robot_id': capture.get('robot_id'),
        'device_id': capture.get('device_id'),
        'capture_id': capture.get('capture_id'),
        'source': 'm55_http_voice_to_server_language_relay',
        'transcript': transcript,
        'confidence': max(0.0, min(1.0, float(confidence))),
        'language_context': {
            'user_facing_text': transcript,
            'operator_facing_reply': (
                '收到，进入安全检查。'
                if classification['kind'] == 'vla_command'
                else '我在，可以继续说。'
            ),
            'requires_vla_action': classification['requires_vla_action'],
            'route': classification['route'],
        },
        'utterance_classification': classification,
        'allowed_next_step': (
            'server_vla_l_context_over_http'
            if classification['kind'] == 'vla_command'
            else 'tts_conversation_reply_only'
        ),
        'forbidden_outputs': [
            'can_frame',
            'motor_current',
            'motor_torque',
            'raw_motor_position',
            'raw_motor_velocity',
            'm33_safety_override',
            'direct_motor_command',
        ],
        'control_boundary': 'vla_language_only_not_motion_permission',
    }


def make_m55_http_voice_relay_request(
    capture: dict[str, object],
    project_id: str = DEFAULT_PROJECT_ID,
    relay_base_url: str = DEFAULT_RELAY_BASE_URL,
    robot_id: str | None = None,
    device_id: str | None = None,
    transcript: str | None = None,
) -> dict[str, object]:
    resolved_robot_id = robot_id or str(capture.get('robot_id') or '')
    resolved_device_id = device_id or str(capture.get('device_id') or '')
    url = (
        relay_base_url.rstrip('/')
        + f'/api/rehab-arm/v1/projects/{project_id}/devices/{resolved_device_id}/model/relay'
    )
    text = transcript if transcript is not None else str(capture.get('transcript') or '')
    return {
        'schema_version': 'm55_http_voice_relay_request_v1',
        'method': 'POST',
        'url': url,
        'auth': {
            'type': 'bearer_relay_token',
            'token_storage': 'm55_secure_or_runtime_config_not_vendor_api_key',
        },
        'content_type': 'application/json_or_multipart_form_data',
        'body_json': {
            'schema_version': 'model_relay_request_v1',
            'robot_id': resolved_robot_id,
            'device_id': resolved_device_id,
            'project_id': project_id,
            'input_type': 'vla_language_from_voice',
            'prompt': '把唤醒后的语音输入分类为日常聊天或康复指令；聊天只回复，指令只生成 VLA 的 L 部分。',
            'context_refs': {
                'capture_id': capture.get('capture_id'),
                'voice_audio_ref': capture.get('audio_ref', 'm55_http_upload_audio_or_features'),
                'local_transcript': text,
                'wake_detected': capture.get('wake_detected', False),
                'wake_phrase': capture.get('wake_phrase'),
            },
            'requested_outputs': [
                'language_context',
                'voice_intent',
                'operator_facing_reply',
                'utterance_classification',
            ],
            'forbidden_outputs': [
                'can_frame',
                'motor_current',
                'motor_torque',
                'raw_motor_position',
                'raw_motor_velocity',
                'm33_safety_override',
                'direct_motor_command',
            ],
            'control_boundary': 'vla_language_http_relay_only_not_motion_permission',
        },
        'transport_boundary': 'm55_wifi_http_not_can',
        'control_boundary': 'http_request_plan_only_not_motion_permission',
    }


def make_voice_relay_payload(
    capture: dict[str, object],
    result_label: str,
    transcript: str = '',
    confidence: float = 0.0,
    model_id: str = 'm55_voice_asr_v1',
    result_code: int | None = None,
    now: float | None = None,
) -> dict[str, object]:
    classification = classify_voice_utterance(transcript)
    label_to_code = {
        'voice_none': 0,
        'voice_start_request': 1,
        'voice_pause_request': 2,
        'voice_stop_request': 3,
        'voice_pain_or_discomfort': 4,
        'voice_free_text': 5,
        'wake_start_request': 1,
        'voice_daily_chat': 5,
        'voice_rehab_task_request': 5,
    }
    resolved_code = label_to_code.get(result_label, 5) if result_code is None else int(result_code)
    return {
        'schema_version': VOICE_RELAY_SCHEMA_VERSION,
        'ts_unix': time.time() if now is None else now,
        'robot_id': capture.get('robot_id'),
        'device_id': capture.get('device_id'),
        'capture_id': capture.get('capture_id'),
        'source': 'command_center_voice_api_relay',
        'input_source': capture.get('source'),
        'transcript': transcript,
        'result': {
            'model_id': model_id,
            'label': result_label,
            'result_code': resolved_code,
            'confidence': max(0.0, min(1.0, float(confidence))),
        },
        'utterance_classification': classification,
        'vla_language_context': make_vla_language_context_payload(
            capture,
            transcript=transcript,
            confidence=confidence,
            now=now,
        ),
        'as_model_state': {
            'schema_version': 'rehab_arm_model_state_v1',
            'model_results': [
                {
                    'model_id': model_id,
                    'result_code': resolved_code,
                    'result_name': result_label,
                    'confidence': max(0.0, min(1.0, float(confidence))),
                    'fresh': True,
                    'detected': result_label not in ('voice_none', 'none'),
                    'suggestion_only': True,
                    'transcript': transcript,
                }
            ],
            'control_boundary': 'model_suggestion_only_not_motion_permission',
        },
        'control_boundary': 'voice_relay_only_not_motion_permission',
    }


def make_tts_playback_request(
    robot_id: str,
    device_id: str,
    text: str,
    target: str = 'm55_speaker',
    voice: str = 'rehab_assistant_zh',
    request_id: str | None = None,
    now: float | None = None,
) -> dict[str, object]:
    timestamp = time.time() if now is None else now
    if request_id is None:
        request_id = stable_capture_id(robot_id, device_id, now=timestamp).replace('__', '_tts_', 1)
    return {
        'schema_version': TTS_REQUEST_SCHEMA_VERSION,
        'ts_unix': timestamp,
        'robot_id': robot_id,
        'device_id': device_id,
        'request_id': request_id,
        'source': 'command_center_llm_tts_relay',
        'target': target,
        'voice': voice,
        'text': text,
        'audio_format': DEFAULT_AUDIO_FORMAT,
        'sample_rate_hz': DEFAULT_SAMPLE_RATE_HZ,
        'transport': 'server_http_or_websocket_tts_to_m55_speaker_not_can',
        'control_boundary': 'tts_feedback_only_not_motion_permission',
    }


def build_voice_pipeline_plan(
    robot_id: str,
    device_id: str,
    prompt_text: str = '开始训练',
    wake_phrase: str = DEFAULT_WAKE_PHRASE,
    now: float | None = None,
) -> dict[str, object]:
    timestamp = time.time() if now is None else now
    capture = make_voice_capture_payload(
        robot_id=robot_id,
        device_id=device_id,
        wake_phrase=wake_phrase,
        wake_detected=True,
        confidence=0.95,
        transcript=prompt_text,
        duration_ms=1200,
        now=timestamp,
    )
    classification = classify_voice_utterance(prompt_text)
    relay = make_voice_relay_payload(
        capture,
        result_label=str(classification['label']),
        transcript=prompt_text,
        confidence=0.9,
        now=timestamp,
    )
    http_request = make_m55_http_voice_relay_request(
        capture,
        robot_id=robot_id,
        device_id=device_id,
        transcript=prompt_text,
    )
    tts = make_tts_playback_request(
        robot_id=robot_id,
        device_id=device_id,
        text='收到，请保持放松，等待安全检查通过。',
        now=timestamp,
    )
    return {
        'schema_version': VOICE_PIPELINE_PLAN_SCHEMA_VERSION,
        'ts_unix': timestamp,
        'robot_id': robot_id,
        'device_id': device_id,
        'wake_phrase': wake_phrase,
        'wake_model_policy': DEFAULT_WAKE_MODEL_POLICY,
        'official_reference': {
            'name': INFINEON_LOCAL_VOICE_EXAMPLE,
            'repo': 'https://github.com/Infineon/mtb-example-psoc-edge-mains-powered-local-voice',
            'local_reference_path': 'D:/RT-ThreadStudio/workspace/_ifx_local_voice',
            'pipeline': [
                'CM55 PDM microphone ISR creates 10 ms PCM frames',
                'audio_feed_interface feeds frames into DEEPCRAFT audio enhancement',
                'inferencing_interface runs wake word and command recognition',
                'control_task receives map_id and handles LEDs/I2S/application events',
            ],
        },
        'portable_model_sources': [
            'Infineon PSOC Edge local voice example for board audio/I2S/PDM/VA pipeline',
            'TensorFlow Lite Micro micro_speech only as a minimal official fallback runtime',
            'OHF/ESPHome micro-wake-word only as an open-source custom wake-word fallback',
        ],
        'portability_rules': [
            'keep audio capture, feature extraction, model runner, result publisher, and transport separated',
            'do not revive the old custom wake route as the main path; keep it as diagnostics only',
            'port the official CM55 PDM/AFE/inferencing/control-task shape into the current wifi project modules',
            'convert selected fallback .tflite model to a C array and load it through model_manager slot APIs',
            'publish local wake/model event summaries through M33/M55 IPC and /rehab_arm/model_state only for observation',
            'send cloud chat, ASR, VLA-L, and TTS over M55 WiFi HTTP/WebSocket; do not route cloud voice through CAN',
            'keep cloud ASR/TTS optional; server command center is an API relay and VLA context builder, not a real-time controller',
        ],
        'm55_expected_commands': [
            'official_voice_self_test',
            'pdm_mic_self_test',
            'local_voice_listen',
            'voice_pipeline_status',
        ],
        'pipeline': [
            {
                'step': 'm55_capture_raw_pcm',
                'owner': 'M55 voice_service',
                'payload': capture,
            },
            {
                'step': 'm55_http_post_voice_to_server',
                'owner': 'M55 WiFi HTTP client -> server command center',
                'payload': http_request,
            },
            {
                'step': 'server_classify_chat_or_vla_l',
                'owner': 'server command center',
                'payload': relay,
            },
            {
                'step': 'llm_tts_playback',
                'owner': 'server command center -> M55 speaker path over HTTP/WebSocket',
                'payload': tts,
            },
        ],
        'utterance_routing': {
            'daily_chat': 'TTS reply only; do not enter VLA action planning',
            'vla_command': 'enter VLA L context over HTTP; fuse with NanoPi vision V and robot state before A',
            'current_kind': classification['kind'],
            'current_route': classification['route'],
            'cloud_voice_transport': 'm55_wifi_http_not_can',
        },
        'forbidden_outputs': ['can_frame', 'motor_current', 'motor_torque', 'motion_allowed'],
        'control_boundary': 'voice_pipeline_plan_only_not_motion_permission',
    }
