from pathlib import Path
import re
import unittest


M55_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = M55_ROOT / "applications"


def function_body(source, name):
    match = re.search(r"\b%s\s*\([^)]*\)\s*\{" % re.escape(name), source)
    assert match, "%s() not found" % name
    start = match.end()
    depth = 1
    i = start
    while i < len(source) and depth:
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
        i += 1
    assert depth == 0, "%s() body is not balanced" % name
    return source[start : i - 1]


def macro_value(source, name):
    match = re.search(r"^\s*#define\s+%s\s+\(?([A-Za-z0-9_+ ]+)\)?\s*$" % re.escape(name), source, re.M)
    assert match, "%s macro not found" % name
    return re.sub(r"\s+", "", match.group(1))


class EmgIntentBridgeContractTest(unittest.TestCase):
    def test_emg_bridge_consumes_shared_emg_stream_and_publishes_intent(self):
        source_path = APP_DIR / "emg_intent_bridge.cpp"
        self.assertTrue(source_path.exists(), f"missing EMG bridge: {source_path}")
        text = source_path.read_text(encoding="utf-8")

        required = [
            "MODEL_INPUT_SRC_EMG",
            "MODEL_INPUT_FMT_UINT16",
            "#define EMG_INTENT_PHYSICAL_CHANNELS 4U",
            "#define EMG_INTENT_MODEL_CHANNELS 3U",
            "g_m33_m55_pcm_shared",
            "m33_m55_shared_pcm_invalidate_payload",
            "intent_tflm_runtime_infer_int8",
            "model_result_publish",
            "MODEL_CODE_EMG_INTENT",
            "EMG_INTENT_REST_INDEX",
        ]
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, text)

        self.assertNotIn("GYRO", text)
        self.assertNotIn("ACCEL", text)
        self.assertNotIn("MODEL_INPUT_SRC_IMU", text)

    def test_emg_bridge_uses_training_preprocess_and_quantization_contract(self):
        text = (APP_DIR / "emg_intent_bridge.cpp").read_text(encoding="utf-8")

        self.assertIn("#define EMG_INTENT_INPUT_SCALE 0.05868540704250336f", text)
        self.assertIn("#define EMG_INTENT_INPUT_ZERO_POINT -47", text)
        self.assertIn("#define EMG_INTENT_REST_INDEX 1", text)
        self.assertRegex(text, r"kFeatureMeans\[INTENT_TFLM_FEATURE_COUNT\]")
        self.assertRegex(text, r"kFeatureStds\[INTENT_TFLM_FEATURE_COUNT\]")
        self.assertIn("features[cursor++] = (float)frame_samples", text)
        self.assertIn("features[cursor++] = (float)stale_count", text)
        self.assertIn("stream->reserved0", text)
        self.assertIn("stride_channels", text)
        self.assertRegex(text, r"input\[i\]\s*=\s*emg_quantize_feature")

    def test_tflm_runtime_wraps_int8_model_for_reuse(self):
        header = (APP_DIR / "intent_tflm_runtime.h").read_text(encoding="utf-8")
        source = (APP_DIR / "intent_tflm_runtime.cpp").read_text(encoding="utf-8")

        self.assertIn("#define INTENT_TFLM_FEATURE_COUNT 21", header)
        self.assertIn("#define INTENT_TFLM_CLASS_COUNT 3", header)
        self.assertIn('"elbow_curl"', source)
        self.assertIn('"rest"', source)
        self.assertIn('"shoulder_flex"', source)
        self.assertNotIn('"elbow_extend"', source)
        self.assertNotIn('"elbow_flex"', source)
        self.assertIn("intent_tflm_runtime_infer_int8", header)
        self.assertIn('#include "intent_model_int8.h"', source)
        self.assertIn("tflite::MicroInterpreter", source)
        self.assertIn("MicroMutableOpResolver<2>", source)
        self.assertIn("AddFullyConnected()", source)
        self.assertIn("AddSoftmax()", source)
        self.assertIn("Invoke()", source)

    def test_voice_service_routes_emg_stream_before_audio_pcm(self):
        text = (APP_DIR / "voice_service.c").read_text(encoding="utf-8")

        self.assertIn('#include "emg_intent_bridge.h"', text)
        emg_pos = text.index("MODEL_INPUT_SRC_EMG")
        audio_pos = text.index("MODEL_INPUT_SRC_AUDIO_PCM", emg_pos)
        self.assertLess(emg_pos, audio_pos)
        self.assertIn("emg_intent_bridge_handle_stream", text)

    def test_m55_pcm_shared_block_is_linked_to_soc_shared_memory(self):
        comm = (APP_DIR / "m33_m55_comm.c").read_text(encoding="utf-8")
        linker = (M55_ROOT / "board" / "linker_scripts" / "link.ld").read_text(encoding="utf-8")

        self.assertIn('section(".ipc_stream_shared")', comm)
        self.assertIn(".ipc_stream_shared(NOLOAD)", linker)
        self.assertIn("} > m33_m55_shared", linker)
        self.assertIn("m33_m55_shared : ORIGIN = 0x261C0000", linker)

    def test_shared_pcm_consumers_invalidate_header_before_seq_check(self):
        emg = (APP_DIR / "emg_intent_bridge.cpp").read_text(encoding="utf-8")
        voice = (APP_DIR / "voice_service.c").read_text(encoding="utf-8")

        for name, text, marker in (
            ("emg", emg, "emg_intent_bridge_handle_stream"),
            ("voice", voice, "voice_service_accept_shared_pcm"),
        ):
            with self.subTest(consumer=name):
                body = function_body(text, marker)
                self.assertIn("m33_m55_shared_pcm_invalidate_header", body)
                self.assertLess(
                    body.index("m33_m55_shared_pcm_invalidate_header"),
                    body.index("stream->chunk_index != g_m33_m55_pcm_shared.seq"),
                )

    def test_main_primes_emg_intent_and_starts_ipc_bridge_without_cloud_voice_success(self):
        main = (APP_DIR / "main.c").read_text(encoding="utf-8")

        self.assertIn('#include "emg_intent_bridge.h"', main)
        self.assertIn("emg_intent_bridge_init()", main)
        self.assertIn("xiaozhi_bridge_thread_start()", main)
        self.assertLess(main.index("emg_intent_bridge_init()"), main.index("xiaozhi_bridge_thread_start()"))

    def test_legacy_imu_bridge_is_not_built_by_default(self):
        sconscript_path = APP_DIR / "edge_ai_bridge" / "SConscript"
        if not sconscript_path.exists():
            return
        sconscript = sconscript_path.read_text(encoding="utf-8")

        self.assertIn("EDGE_AI_USING_LEGACY_IMU_BRIDGE", sconscript)
        self.assertRegex(sconscript, r"src\s*=\s*Glob\('\*\.c'\)\s*if\s*GetDepend")

    def test_m33_m55_ipc_contract_matches_cm33_morning_baseline(self):
        comm = (APP_DIR / "m33_m55_comm.c").read_text(encoding="utf-8")

        internal_channel = macro_value(comm, "M33_M55_IPC_INTERNAL_CHANNEL")
        queue_channel = macro_value(comm, "M33_M55_IPC_QUEUE_CHANNEL")
        instance_sema = macro_value(comm, "M33_M55_IPC_INSTANCE_SEMA")
        sema_irq = macro_value(comm, "M33_M55_IPC_IRQ_SEMA")
        queue_irq = macro_value(comm, "M33_M55_IPC_IRQ_QUEUE")

        self.assertEqual("MTB_IPC_CHAN_1", internal_channel)
        self.assertEqual("MTB_IPC_CHAN_0", queue_channel)
        self.assertEqual("5UL", instance_sema)
        self.assertEqual("MTB_IPC_IRQ_USER+4", sema_irq)
        self.assertEqual("MTB_IPC_IRQ_USER+5", queue_irq)
        self.assertNotIn("MTB_IPC_CHANNEL_M33_M55_QUEUE", comm)
        self.assertNotIn("MTB_IPC_SEMA_NUM_M33_M55_INSTANCE", comm)


if __name__ == "__main__":
    unittest.main()
