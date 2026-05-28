from __future__ import annotations


def psoc_motion_gate_detail(
    status_payload: dict[str, object] | None,
    allow_bench_motion: bool = False,
) -> tuple[bool, str]:
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
    if (
        allow_bench_motion
        and state == 'ok'
        and control_mode == 'bench_armed'
        and detail in (None, '', 'none')
        and error_code == 0
    ):
        return True, 'bench motion explicitly allowed by NanoPi parameter'

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


def fresh_motor_feedback_gate_detail(
    last_fresh_motor_status_age_sec: float | None,
    timeout_sec: float,
    fresh_motor_status_count: int,
) -> tuple[bool, str]:
    """Return whether NanoPi has recent enough measured joint feedback.

    M33 may publish placeholder/stale motor slots while real motor feedback is
    missing. NanoPi must not use those stale slots as proof that the robot
    posture is known before accepting a trajectory.
    """
    if fresh_motor_status_count <= 0 or last_fresh_motor_status_age_sec is None:
        return False, 'no fresh M33 motor feedback received'
    if last_fresh_motor_status_age_sec > timeout_sec:
        return (
            False,
            f'fresh M33 motor feedback stale for {last_fresh_motor_status_age_sec:.1f}s',
        )
    return True, 'fresh M33 motor feedback available'
