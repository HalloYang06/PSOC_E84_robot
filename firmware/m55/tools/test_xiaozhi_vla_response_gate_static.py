from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = (ROOT / "applications" / "xiaozhi_voice_relay.h").read_text(encoding="utf-8")
SOURCE = (ROOT / "applications" / "xiaozhi_voice_relay.c").read_text(encoding="utf-8")


def test_vla_response_carries_explicit_server_event_identity():
    assert "char event_id[65];" in HEADER
    assert 'json_get_top_string(json, "event_id", response->event_id' in SOURCE
    assert 'json_get_top_string(json, "command_id", response->event_id' in SOURCE


def test_only_exact_vla_kind_is_classified_as_control():
    assert 'rt_strcmp(kind, "vla_command") == 0' in SOURCE
    assert 'rt_strstr(kind, "command")' not in SOURCE


def test_control_metadata_requires_complete_top_level_json_without_truncation():
    assert "json_object_complete" in SOURCE
    assert "JSON_TOP_STRING_TRUNCATED" in SOURCE
    assert 'json_get_top_string(json, "kind", kind' in SOURCE
    assert 'json_get_top_string(json, "language_context", response->language_context' in SOURCE
    assert 'json_get_top_string(json, "voice_intent", response->language_context' in SOURCE
    assert "json_get_string(" not in SOURCE
