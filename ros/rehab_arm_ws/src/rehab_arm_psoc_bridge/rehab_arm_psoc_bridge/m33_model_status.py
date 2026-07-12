from __future__ import annotations

M33_MODEL_STATUS_ID = 0x323
M33_MODEL_STATUS_MARKER = 0xB5
M33_MODEL_STATUS_FLAG_FRESH = 0x01
M33_MODEL_STATUS_FLAG_DETECTED = 0x02
M33_MODEL_STATUS_FLAG_SUGGESTION_ONLY = 0x80

MODEL_NAMES = {
    1: 'm55_wake_word_v1',
    2: 'm55_emg_intent_v1',
    3: 'm55_fatigue_v1',
    4: 'm55_voice_asr_v1',
}

RESULT_NAMES = {
    0: 'none',
    1: 'wake_start_request',
}

RESULT_NAMES_BY_MODEL = {
    1: {
        0: 'none',
        1: 'wake_start_request',
    },
    2: {
        0: 'emg_none',
        1: 'emg_relax',
        2: 'emg_flex_intent',
        3: 'emg_extend_intent',
        4: 'emg_stop_or_resist',
        5: 'emg_contact_bad',
    },
    3: {
        0: 'fatigue_none',
        1: 'fatigue_low',
        2: 'fatigue_medium',
        3: 'fatigue_high',
    },
    4: {
        0: 'voice_none',
        1: 'voice_start_request',
        2: 'voice_pause_request',
        3: 'voice_stop_request',
        4: 'voice_pain_or_discomfort',
        5: 'voice_free_text',
    },
}


def result_name_for_model(model_code: int, result_code: int) -> str:
    names = RESULT_NAMES_BY_MODEL.get(model_code)
    if names is not None:
        return names.get(result_code, f'unknown_result_{result_code}')
    return RESULT_NAMES.get(result_code, f'unknown_result_{result_code}')


def parse_m33_model_status_frame(can_id: int, data: bytes) -> dict[str, object]:
    payload: dict[str, object] = {
        'raw_can_id': f'0x{can_id:03X}',
        'raw_data': data.hex().upper(),
        'valid': False,
    }
    if can_id != M33_MODEL_STATUS_ID:
        payload['detail'] = 'unexpected_can_id'
        return payload
    if len(data) < 8:
        payload['detail'] = 'short_frame'
        return payload
    if data[0] != M33_MODEL_STATUS_MARKER:
        payload['detail'] = 'bad_marker'
        payload['marker'] = data[0]
        return payload

    model_code = data[2]
    result_code = data[3]
    confidence_percent = data[4]
    flags = data[5]
    window_ms = data[6] * 10

    payload.update(
        {
            'valid': True,
            'detail': 'ok',
            'marker': data[0],
            'seq': data[1],
            'model_code': model_code,
            'model_name': MODEL_NAMES.get(model_code, f'unknown_model_{model_code}'),
            'result_code': result_code,
            'result_name': result_name_for_model(model_code, result_code),
            'confidence': min(confidence_percent, 100) / 100.0,
            'confidence_percent': min(confidence_percent, 100),
            'flags': flags,
            'fresh': bool(flags & M33_MODEL_STATUS_FLAG_FRESH),
            'detected': bool(flags & M33_MODEL_STATUS_FLAG_DETECTED),
            'suggestion_only': bool(flags & M33_MODEL_STATUS_FLAG_SUGGESTION_ONLY),
            'window_ms': window_ms,
            'source_detail': data[7],
            'control_boundary': 'model_suggestion_only_not_motion_permission',
        }
    )
    return payload
