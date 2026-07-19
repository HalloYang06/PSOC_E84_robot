from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER_PATH = ROOT / "applications" / "voice_rehab_ipc_sender.h"
SOURCE_PATH = ROOT / "applications" / "voice_rehab_ipc_sender.c"


def test_sender_is_fixed_storage_epoch_fallback_and_nonblocking():
    header = HEADER_PATH.read_text(encoding="utf-8")
    source = SOURCE_PATH.read_text(encoding="utf-8")

    assert "VOICE_REHAB_EVENT_HISTORY_DEPTH 8U" in header
    assert "VOICE_REHAB_PENDING_DEPTH 8U" in header
    assert 'rt_device_find("urandom")' in source
    assert "voice_rehab_make_boot_epoch" in source
    assert "rt_tick_get()" in source
    assert "rt_thread_self()" in source
    assert "return -RT_ENOSYS" not in source
    assert "m33_m55_comm_try_publish" in source
    assert "m33_m55_comm_publish(" not in source
    assert "rt_malloc" not in source


def test_sender_uses_exact_event_and_payload_replay_protection():
    source = SOURCE_PATH.read_text(encoding="utf-8")

    assert "rt_strcmp(entry->event_id, event_id)" in source
    assert "rt_strcmp(entry->payload, payload)" in source
    assert "duplicate_event" in source
    assert "conflicting_event" in source
    assert "next_request_id == UINT32_MAX" in source


def test_sender_tracks_result_identity_without_retrying_commands():
    header = HEADER_PATH.read_text(encoding="utf-8")
    source = SOURCE_PATH.read_text(encoding="utf-8")

    assert "voice_rehab_ipc_sender_handle_result" in header
    assert "result->boot_epoch != s_sender.boot_epoch" in source
    assert "voice_rehab_find_pending(result->request_id)" in source
    assert "pending->mode != result->requested_mode" in source
    assert "pending->joint_mask != result->joint_mask" in source
    assert "last_result_status" in source
    assert "retry" not in source.lower()


def test_sender_retries_only_pre_publish_busy_contention():
    source = SOURCE_PATH.read_text(encoding="utf-8")

    assert "VOICE_REHAB_PUBLISH_BUSY_ATTEMPTS 2U" in source
    assert "ret == -RT_EBUSY" in source
    assert "rt_thread_yield()" in source


def test_sender_expires_unknown_results_and_exposes_shell_diagnostics():
    header = HEADER_PATH.read_text(encoding="utf-8")
    source = SOURCE_PATH.read_text(encoding="utf-8")

    assert "result_timeout" in header
    assert "VOICE_REHAB_RESULT_TIMEOUT_MS 1500U" in source
    assert "voice_rehab_expire_pending_locked" in source
    assert "cmd_voice_rehab_ipc_debug" in source
    assert "MSH_CMD_EXPORT(cmd_voice_rehab_ipc_debug" in source
