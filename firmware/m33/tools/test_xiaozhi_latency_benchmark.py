import unittest

from xiaozhi_latency_benchmark import LatencyOutputParser, parse_latency_line, summarize


class XiaoZhiLatencyBenchmarkTests(unittest.TestCase):
    def test_parses_current_multiline_shell_output(self) -> None:
        parser = LatencyOutputParser()
        lines = (
            "[m55qa] xz_latency ipc_seq=5633 turn_seq=4 flags=0xd source=manual qa_text=1 age_ticks=12",
            "[m55qa] xz_latency capture wake_listen_ms=0 voice_stop_ms=901",
            "[m55qa] xz_latency cloud stop_stt_ms=22 stt_llm_ms=310",
            "[m55qa] xz_latency playback llm_tts_ms=420 tts_packet_ms=1869 packet_write_ms=123",
            "[m55qa] xz_latency total speech_audio_ms=3645 wake_audio_ms=3650",
        )

        row = None
        for line in lines:
            row = parser.feed_line(line) or row

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["seq"], 5633)
        self.assertEqual(row["turn"], 4)
        self.assertEqual(row["eou"], 901)
        self.assertEqual(row["stop_audio"], 2744)
        self.assertEqual(row["speech_audio"], 3645)

    def test_preserves_unavailable_stages_as_none(self) -> None:
        parser = LatencyOutputParser()
        lines = (
            "[m55qa] xz_latency ipc_seq=4747 turn_seq=3 flags=0x3 source=real_wake qa_text=0 age_ticks=4",
            "[m55qa] xz_latency capture wake_listen_ms=1 voice_stop_ms=NA",
            "[m55qa] xz_latency cloud stop_stt_ms=NA stt_llm_ms=NA",
            "[m55qa] xz_latency playback llm_tts_ms=NA tts_packet_ms=2522 packet_write_ms=114",
            "[m55qa] xz_latency total speech_audio_ms=2647 wake_audio_ms=3608",
        )

        row = None
        for line in lines:
            row = parser.feed_line(line) or row

        self.assertIsNotNone(row)
        assert row is not None
        self.assertIsNone(row["eou"])
        self.assertIsNone(row["stop_stt"])
        self.assertIsNone(row["stop_audio"])
        summary = summarize([row])
        self.assertEqual(summary["speech_audio_ms"]["p50"], 2647)
        self.assertEqual(summary["stop_stt_ms"]["count"], 0)

    def test_keeps_wen_single_line_format_compatible(self) -> None:
        row = parse_latency_line(
            "[m55qa] xz_latency seq=8 turn=3 flags=0x3 wake_listen=20 eou=901 "
            "stop_stt=400 stt_llm=500 llm_tts=600 tts_packet=700 packet_write=80 "
            "speech_audio=3181 wake_audio=4200 age_ticks=4"
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["turn"], 3)
        self.assertEqual(row["stop_audio"], 2280)


if __name__ == "__main__":
    unittest.main()
