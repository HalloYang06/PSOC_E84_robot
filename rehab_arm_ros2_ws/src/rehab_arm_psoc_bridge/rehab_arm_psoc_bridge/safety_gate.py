from __future__ import annotations


def psoc_motion_gate_detail(status_payload: dict[str, object] | None) -> tuple[bool, str]:
    """Return whether NanoPi may accept/send trajectory targets.

    M33 is the final safety authority. NanoPi must treat `motion_allowed` as the
    only positive permission bit from `0x322`; legacy `state=ok` is status
    compatibility, not motion permission.
    """
    if status_payload is None:
        return False, 'no PSoC status received'

    motion_allowed = status_payload.get('motion_allowed')
    if motion_allowed is True:
        return True, 'PSoC motion_allowed true'

    state = status_payload.get('state')
    detail = status_payload.get('detail')
    control_mode = status_payload.get('control_mode')
    error_code = status_payload.get('error_code')
    protocol_version = status_payload.get('protocol_version')

    parts = ['PSoC motion_allowed is not true']
    if isinstance(protocol_version, int):
        parts.append(f'protocol_version={protocol_version}')
    if isinstance(state, str):
        parts.append(f'state={state}')
    if isinstance(control_mode, str):
        parts.append(f'control_mode={control_mode}')
    if isinstance(detail, str) and detail:
        parts.append(f'detail={detail}')
    if isinstance(error_code, int) and error_code != 0:
        parts.append(f'error_code={error_code}')
    return False, ', '.join(parts)
