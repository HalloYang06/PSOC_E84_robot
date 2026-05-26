from __future__ import annotations


PSOC_STATUS_MARKER = 0xA5

SAFETY_STATE_NAMES = {
    0: 'ok',
    1: 'limited',
    2: 'emergency_stop',
    3: 'fault',
}

CONTROL_MODE_NAMES = {
    0: 'boot',
    1: 'logging_only',
    2: 'standby',
    3: 'armed',
    4: 'active',
    5: 'emergency_stop',
}

DETAIL_CODE_NAMES = {
    0: 'none',
    1: 'heartbeat_timeout',
    2: 'unsupported_command',
    3: 'unknown_joint',
    4: 'target_out_of_limit',
    5: 'velocity_out_of_limit',
    6: 'torque_out_of_limit',
    7: 'emergency_stop',
    8: 'power_fault',
    9: 'motor_fault',
    10: 'logging_only_no_motor_output',
    11: 'joint_uncalibrated',
}


def _looks_like_status_v2(data: bytes) -> bool:
    if len(data) < 8:
        return False
    if data[0] != PSOC_STATUS_MARKER:
        return False
    if data[4] not in SAFETY_STATE_NAMES:
        return False
    if data[5] not in CONTROL_MODE_NAMES:
        return False
    if data[6] not in DETAIL_CODE_NAMES:
        return False
    return True


def parse_psoc_status_payload(data: bytes) -> dict[str, object]:
    payload: dict[str, object] = {
        'source': 'psoc',
        'id_hex': '0x322',
        'data': data.hex().upper(),
    }

    if len(data) < 4:
        payload.update({
            'state': 'fault',
            'detail': 'PSoC status too short',
            'motion_allowed': False,
        })
        return payload

    marker = data[0]
    seq = data[1]
    motors = data[2]
    error_code = data[3]
    marker_ok = marker == PSOC_STATUS_MARKER

    payload.update({
        'marker': marker,
        'seq': seq,
        'motors': motors,
        'error_code': error_code,
    })

    if not marker_ok:
        payload.update({
            'state': 'fault',
            'detail': 'invalid PSoC status marker',
            'motion_allowed': False,
        })
        return payload

    if _looks_like_status_v2(data):
        safety_code = data[4]
        mode_code = data[5]
        detail_code = data[6]
        heartbeat_age_100ms = data[7]
        state = SAFETY_STATE_NAMES[safety_code]
        detail = DETAIL_CODE_NAMES[detail_code]
        if error_code != 0 and state == 'ok':
            state = 'fault'
            detail = f'error_code={error_code}'
        payload.update({
            'protocol_version': 2,
            'state': state,
            'safety_code': safety_code,
            'control_mode': CONTROL_MODE_NAMES[mode_code],
            'control_mode_code': mode_code,
            'detail_code': detail_code,
            'detail': detail,
            'detail_semantics': 'last_safety_assessment',
            'last_assessment_detail_code': detail_code,
            'last_assessment_detail': detail,
            'heartbeat_age_ms': heartbeat_age_100ms * 100,
            'motion_allowed': (
                state == 'ok'
                and mode_code in (3, 4)
                and detail_code == 0
                and error_code == 0
            ),
        })
        return payload

    payload.update({
        'protocol_version': 1,
        'state': 'fault' if error_code != 0 else 'ok',
        'status_data': data[4:].hex().upper(),
        'motion_allowed': False,
    })
    return payload
