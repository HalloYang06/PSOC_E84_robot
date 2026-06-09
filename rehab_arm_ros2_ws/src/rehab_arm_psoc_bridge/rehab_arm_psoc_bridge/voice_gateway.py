from __future__ import annotations

import time
from hashlib import sha256


VOICE_CAPTURE_SCHEMA_VERSION = 'voice_capture_v1'
VOICE_RELAY_SCHEMA_VERSION = 'voice_relay_v1'
TTS_REQUEST_SCHEMA_VERSION = 'tts_playback_request_v1'
VOICE_PIPELINE_PLAN_SCHEMA_VERSION = 'rehab_arm_voice_pipeline_plan_v1'

DEFAULT_WAKE_PHRASE = 'xiao_yi_xiao_yi'
DEFAULT_AUDIO_FORMAT = 'pcm_s16le'
DEFAULT_SAMPLE_RATE_HZ = 16000
DEFAULT_CHANNELS = 1
DEFAULT_WAKE_MODEL_POLICY = 'infineon_local_voice_first_then_tflm_or_micro_wake_word'
INFINEON_LOCAL_VOICE_EXAMPLE = 'Infineon PSOC Edge mains-powered local voice'


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


def make_voice_relay_payload(
    capture: dict[str, object],
    result_label: str,
    transcript: str = '',
    confidence: float = 0.0,
    model_id: str = 'm55_voice_asr_v1',
    result_code: int | None = None,
    now: float | None = None,
) -> dict[str, object]:
    label_to_code = {
        'voice_none': 0,
        'voice_start_request': 1,
        'voice_pause_request': 2,
        'voice_stop_request': 3,
        'voice_pain_or_discomfort': 4,
        'voice_free_text': 5,
        'wake_start_request': 1,
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
        'transport': 'server_ws_binary_or_m55_tts_audio_to_m33',
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
    relay = make_voice_relay_payload(
        capture,
        result_label='voice_start_request' if '开始' in prompt_text else 'voice_free_text',
        transcript=prompt_text,
        confidence=0.9,
        now=timestamp,
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
            'publish wake/ASR/TTS results through M33/M55 IPC and /rehab_arm/model_state instead of direct motion',
            'keep cloud ASR/TTS optional; server command center is an API relay, not a real-time controller',
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
                'step': 'command_center_voice_api_relay',
                'owner': 'server command center',
                'payload': relay,
            },
            {
                'step': 'llm_tts_playback',
                'owner': 'server command center -> M55/M33 speaker path',
                'payload': tts,
            },
        ],
        'forbidden_outputs': ['can_frame', 'motor_current', 'motor_torque', 'motion_allowed'],
        'control_boundary': 'voice_pipeline_plan_only_not_motion_permission',
    }
