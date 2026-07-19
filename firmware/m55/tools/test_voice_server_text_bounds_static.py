from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "applications" / "voice_service.c").read_text(encoding="utf-8")


def test_oversize_server_json_is_dropped_instead_of_truncated():
    start = SOURCE.index("static void voice_service_enqueue_server_text")
    end = SOURCE.index("static rt_bool_t voice_service_process_pending_server_text", start)
    body = SOURCE[start:end]

    assert "payload_len >= VOICE_SERVER_TEXT_SLOT_SIZE" in body
    assert "server_text_oversize_drop_count++" in body
    assert "copy_len = payload_len;" in body
    assert "VOICE_SERVER_TEXT_SLOT_SIZE - 1U) : payload_len" not in body
