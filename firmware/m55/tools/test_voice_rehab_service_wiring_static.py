from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "applications" / "voice_service.c").read_text(encoding="utf-8")


def test_voice_service_initializes_fail_closed_sender():
    assert '#include "voice_rehab_ipc_sender.h"' in SOURCE
    assert "voice_rehab_ipc_sender_init()" in SOURCE


def test_vla_and_exact_final_stt_can_publish_rehab_request():
    vla_start = SOURCE.index("if (xiaozhi_response.kind == XIAOZHI_UTTERANCE_VLA_COMMAND)")
    vla_path = SOURCE[vla_start : vla_start + 1800]
    assert "xiaozhi_response.event_id" in vla_path
    assert "xiaozhi_response.language_context" in vla_path
    assert "voice_rehab_ipc_sender_submit_vla" in vla_path

    helper_start = SOURCE.index("static void voice_service_submit_fixed_level_intent")
    helper_end = SOURCE.index("static void voice_service_handle_server_text", helper_start)
    helper = SOURCE[helper_start:helper_end]
    assert helper.index("voice_mode_intent_classify") < helper.index("voice_rehab_ipc_sender_submit_vla")
    assert "VOICE_REHAB_ACTION_SET_MODE" in helper
    assert "VOICE_REHAB_ACTION_LEVEL_UP" in helper
    assert "VOICE_REHAB_ACTION_LEVEL_DOWN" in helper

    stt_start = SOURCE.index('if ((rt_strcmp(type, "stt") == 0)')
    stt_end = SOURCE.index('if (rt_strcmp(type, "tts") == 0)', stt_start)
    stt_path = SOURCE[stt_start:stt_end]
    assert "voice_service_submit_fixed_level_intent(text)" in stt_path
    assert "voice_rehab_ipc_sender_submit_vla" not in stt_path


def test_rehab_result_is_diagnostic_only():
    assert "case MSG_TYPE_REHAB_MODE_RESULT:" in SOURCE
    assert "voice_rehab_ipc_sender_handle_result(&msg->payload.rehab_mode_result)" in SOURCE
