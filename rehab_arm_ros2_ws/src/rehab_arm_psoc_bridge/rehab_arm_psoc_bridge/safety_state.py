from __future__ import annotations


def bridge_safety_payload(state: str, detail: str) -> dict[str, object]:
    return {
        'source': 'psoc_bridge',
        'state': state,
        'control_mode': 'bridge',
        'detail': detail,
        'detail_semantics': 'current_bridge_state',
        'current_detail': detail,
        'motion_allowed': False,
    }
