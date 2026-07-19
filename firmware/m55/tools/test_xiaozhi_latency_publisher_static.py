from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_voice_latency_publisher_is_observation_only_and_nonblocking() -> None:
    voice = (ROOT / "applications" / "voice_service.c").read_text(encoding="utf-8")

    assert "voice_service_latency_begin_turn" in voice
    assert "VOICE_LATENCY_FLAG_REAL_WAKE" in voice
    assert "VOICE_LATENCY_FLAG_MANUAL" in voice
    assert "VOICE_LATENCY_FLAG_QA_TEXT" in voice

    for stage in (
        "rt_tick_t wake_tick",
        "rt_tick_t listen_tick",
        "rt_tick_t last_voice_tick",
        "rt_tick_t stop_tick",
        "rt_tick_t stt_tick",
        "rt_tick_t llm_tick",
        "rt_tick_t tts_start_tick",
        "rt_tick_t first_packet_tick",
    ):
        assert stage in voice

    latency_start = voice.index("static rt_uint32_t voice_service_latency_delta_ms")
    assert "static voice_latency_tracker_t g_voice_latency;" in voice
    assert "g_service.latency_" not in voice
    assert "rt_hw_interrupt_disable()" in voice
    assert "tts_turn_seq" in voice
    assert "first_packet_turn_seq" in voice
    begin_start = voice.index("static void voice_service_latency_begin_turn")
    begin_end = voice.index("static void voice_service_latency_mark_stage", begin_start)
    begin = voice[begin_start:begin_end]
    assert "rt_hw_interrupt_disable()" in begin
    assert "rt_mutex_take" not in begin

    publish_start = voice.index("static void voice_service_latency_publish_first_write")
    publish_end = voice.index("static rt_uint32_t voice_service_text_code4", publish_start)
    publish = voice[publish_start:publish_end]
    assert "g_voice_latency.active" in publish
    assert "g_voice_latency.tts_turn_seq != g_voice_latency.turn_seq" in publish
    assert "g_voice_latency.first_packet_turn_seq != g_voice_latency.turn_seq" in publish
    assert publish.index("snapshot.turn_seq = g_voice_latency.turn_seq") < publish.index(
        "g_voice_latency.publish_claimed = RT_TRUE"
    )
    assert "m33_m55_comm_try_publish(&msg)" in publish
    assert "m33_m55_comm_publish(&msg)" not in publish
    assert "g_voice_latency.publish_fail_count++" in publish
    assert "VOICE_LATENCY_FLAG_VALID" in publish
    assert "VOICE_LATENCY_MS_UNAVAILABLE" in voice[latency_start:publish_end]

    assert voice.count("voice_service_latency_publish_first_write(rt_tick_get());") == 2
    write_positions = []
    start = 0
    while True:
        position = voice.find("written = rt_device_write(g_service.xiaozhi_speaker_dev", start)
        if position < 0:
            break
        write_positions.append(position)
        start = position + 1
    hook_positions = []
    start = 0
    while True:
        position = voice.find("voice_service_latency_publish_first_write(rt_tick_get());", start)
        if position < 0:
            break
        hook_positions.append(position)
        start = position + 1
    assert len(write_positions) == len(hook_positions) == 2
    for write_position, hook_position in zip(write_positions, hook_positions):
        assert write_position < hook_position
        assert "if (written == 0U)" in voice[write_position:hook_position]
    assert voice.count("m33_m55_comm_publish(&msg)") >= 1
    assert "rt_malloc" not in publish
    assert "rt_calloc" not in publish
    assert "rt_thread_create" not in publish

    assert (
        "voice_service_latency_begin_turn(rt_tick_get(),\n"
        "                                     VOICE_LATENCY_FLAG_MANUAL |\n"
        "                                     VOICE_LATENCY_FLAG_QA_TEXT);"
    ) in voice
    assert voice.count("voice_service_latency_mark_stop_before_send();") == 2
    qa = voice[voice.index("m55_qa_text"):]
    assert qa.index("voice_service_latency_mark_stop_before_send();") < qa.index(
        "websocket_client_send_text(json)"
    )
    normal = voice[voice.rindex("static rt_err_t voice_service_send_xiaozhi_listen_stop("):]
    assert normal.index("voice_service_latency_mark_stop_before_send();") < normal.index(
        "websocket_client_send_text(json)"
    )
    assert 'tts_diag latency turn=%lu fail=%lu drop=%lu' in voice

    assert "#define XIAOZHI_EOU_SILENCE_MS       1400U" in voice
    assert "#define VOICE_TTS_PREBUFFER_MIN_SLOTS 2U" in voice
    assert "#define VOICE_TTS_PREBUFFER_MAX_MS   180U" in voice
    assert '"m55-%08lx-%04lx"' not in voice


if __name__ == "__main__":
    test_voice_latency_publisher_is_observation_only_and_nonblocking()
