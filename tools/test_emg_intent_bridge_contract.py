from pathlib import Path
import re
import unittest


M55_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = M55_ROOT / "applications"


class EmgIntentBridgeContractTest(unittest.TestCase):
    def test_emg_bridge_consumes_shared_emg_stream_and_publishes_intent(self):
        source_path = APP_DIR / "emg_intent_bridge.cpp"
        self.assertTrue(source_path.exists(), f"missing EMG bridge: {source_path}")
        text = source_path.read_text(encoding="utf-8")

        required = [
            "MODEL_INPUT_SRC_EMG",
            "MODEL_INPUT_FMT_UINT16",
            "#define EMG_INTENT_CHANNELS 3U",
            "g_m33_m55_pcm_shared",
            "RT_HW_CACHE_INVALIDATE",
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

        self.assertIn("#define EMG_INTENT_INPUT_SCALE 0.013371267355978489f", text)
        self.assertIn("#define EMG_INTENT_INPUT_ZERO_POINT 86", text)
        self.assertRegex(text, r"kFeatureMeans\[INTENT_TFLM_FEATURE_COUNT\]")
        self.assertRegex(text, r"kFeatureStds\[INTENT_TFLM_FEATURE_COUNT\]")
        self.assertIn("features[cursor++] = (float)frame_samples", text)
        self.assertIn("features[cursor++] = (float)stale_count", text)
        self.assertRegex(text, r"input\[i\]\s*=\s*emg_quantize_feature")

    def test_tflm_runtime_wraps_int8_model_for_reuse(self):
        header = (APP_DIR / "intent_tflm_runtime.h").read_text(encoding="utf-8")
        source = (APP_DIR / "intent_tflm_runtime.cpp").read_text(encoding="utf-8")

        self.assertIn("#define INTENT_TFLM_FEATURE_COUNT 20", header)
        self.assertIn("#define INTENT_TFLM_CLASS_COUNT 4", header)
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

    def test_legacy_imu_bridge_is_not_built_by_default(self):
        sconscript_path = APP_DIR / "edge_ai_bridge" / "SConscript"
        if not sconscript_path.exists():
            return
        sconscript = sconscript_path.read_text(encoding="utf-8")

        self.assertIn("EDGE_AI_USING_LEGACY_IMU_BRIDGE", sconscript)
        self.assertRegex(sconscript, r"src\s*=\s*Glob\('\*\.c'\)\s*if\s*GetDepend")


if __name__ == "__main__":
    unittest.main()
