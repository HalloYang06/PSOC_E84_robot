from __future__ import annotations


F103_SENSOR_ID_HEX = '0x7C2'
F103_HEALTH_ID_HEX = '0x7C3'


def parse_f103_sensor_payload(data: bytes) -> dict[str, object]:
    payload: dict[str, object] = {
        'schema_version': 'rehab_arm_sensor_state_v1',
        'source': 'f103_sensor',
        'id_hex': F103_SENSOR_ID_HEX,
        'data': data.hex().upper(),
        'valid': len(data) >= 8,
        'control_boundary': 'telemetry_only_not_motion_permission',
    }
    if len(data) < 8:
        payload['detail'] = 'short_frame'
        payload['dlc'] = len(data)
        return payload

    flags = data[7]
    payload.update({
        'detail': 'ok',
        'emg_raw': int.from_bytes(data[0:2], 'little', signed=False),
        'emg_filtered': int.from_bytes(data[2:4], 'little', signed=True),
        'heart_rate_raw': int.from_bytes(data[4:6], 'little', signed=False),
        'heart_rate_bpm': data[6],
        'flags': flags,
        'flags_hex': f'0x{flags:02X}',
        'emg_contact': bool(flags & 0x01),
        'imu_valid': bool(flags & 0x02),
        'heart_rate_valid': bool(flags & 0x04),
    })
    return payload


def parse_f103_health_payload(data: bytes) -> dict[str, object]:
    payload: dict[str, object] = {
        'schema_version': 'rehab_arm_sensor_health_v1',
        'source': 'f103_health',
        'id_hex': F103_HEALTH_ID_HEX,
        'data': data.hex().upper(),
        'valid': len(data) >= 4,
        'control_boundary': 'telemetry_only_not_motion_permission',
    }
    if len(data) < 4:
        payload['detail'] = 'short_frame'
        payload['dlc'] = len(data)
        return payload

    state_code = data[0]
    error_count = int.from_bytes(data[1:3], 'little', signed=False)
    queue_fill = data[3]
    payload.update({
        'detail': 'ok',
        'state_code': state_code,
        'state': f103_health_state_name(state_code),
        'error_count': error_count,
        'queue_fill': queue_fill,
        'queue_fill_percent': round(queue_fill * 100.0 / 255.0, 2),
    })
    return payload


def f103_health_state_name(state_code: int) -> str:
    return {
        0: 'boot',
        1: 'ok',
        2: 'streaming',
        3: 'limited',
        4: 'fault',
    }.get(state_code, 'unknown')
