from pathlib import Path
import re
import unittest


M55_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = M55_ROOT / "applications"


class IntentTflmSmokeContractTest(unittest.TestCase):
    def test_generated_model_and_golden_headers_exist(self):
        expected_files = [
            APP_DIR / "intent_model_int8.cc",
            APP_DIR / "intent_model_int8.h",
            APP_DIR / "intent_golden_samples.cc",
            APP_DIR / "intent_golden_samples.h",
        ]

        for path in expected_files:
            with self.subTest(path=str(path)):
                self.assertTrue(path.exists(), f"missing generated artifact: {path}")

    def test_smoke_command_wires_tflm_to_golden_samples(self):
        source_path = APP_DIR / "intent_tflm_smoke.cpp"
        self.assertTrue(source_path.exists(), f"missing smoke command: {source_path}")
        text = source_path.read_text(encoding="utf-8")

        required_fragments = [
            '#include "intent_model_int8.h"',
            '#include "intent_golden_samples.h"',
            "tflite::GetModel",
            "TFLITE_SCHEMA_VERSION",
            "tflite::MicroInterpreter",
            "tflite::MicroMutableOpResolver<2>",
            "AddFullyConnected()",
            "AddSoftmax()",
            "AllocateTensors()",
            "Invoke()",
            "g_intent_golden_input",
            "g_intent_golden_expected_output",
            "g_intent_golden_expected_indices",
            "MSH_CMD_EXPORT(intent_tflm_smoke",
        ]

        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, text)

    def test_smoke_command_checks_tensor_shape_and_prediction(self):
        source_path = APP_DIR / "intent_tflm_smoke.cpp"
        self.assertTrue(source_path.exists(), f"missing smoke command: {source_path}")
        text = source_path.read_text(encoding="utf-8")

        self.assertRegex(text, r"input->bytes\s*!=\s*\(size_t\)g_intent_golden_feature_count")
        self.assertRegex(text, r"output->bytes\s*!=\s*\(size_t\)g_intent_golden_class_count")
        self.assertRegex(text, r"predicted_index\s*!=\s*expected_index")
        self.assertRegex(text, r"abs_i32\([^)]*expected_score")
        self.assertIn("rt_malloc_align", text)
        self.assertNotIn("static uint8_t g_tensor_arena[kTensorArenaBytes]", text)

    def test_sconscript_compiles_generated_cc_files(self):
        sconscript = (APP_DIR / "SConscript").read_text(encoding="utf-8")

        self.assertRegex(sconscript, r"Glob\(['\"]\*\.cc['\"]\)")

    def test_model_source_exports_expected_symbols(self):
        source = (APP_DIR / "intent_model_int8.cc").read_text(encoding="utf-8")
        header = (APP_DIR / "intent_model_int8.h").read_text(encoding="utf-8")

        self.assertRegex(source, r"extern\s+const\s+unsigned\s+char\s+g_intent_model_int8_tflite\[\]")
        self.assertRegex(source, r"extern\s+const\s+unsigned\s+int\s+g_intent_model_int8_tflite_len")
        self.assertRegex(header, r"extern\s+const\s+unsigned\s+char\s+g_intent_model_int8_tflite\[\]")
        self.assertRegex(header, r"extern\s+const\s+unsigned\s+int\s+g_intent_model_int8_tflite_len")

    def test_golden_source_exports_expected_symbols(self):
        source = (APP_DIR / "intent_golden_samples.cc").read_text(encoding="utf-8")
        header = (APP_DIR / "intent_golden_samples.h").read_text(encoding="utf-8")

        for symbol in [
            "g_intent_golden_sample_count",
            "g_intent_golden_feature_count",
            "g_intent_golden_class_count",
            "g_intent_golden_input",
            "g_intent_golden_expected_output",
            "g_intent_golden_expected_indices",
        ]:
            with self.subTest(symbol=symbol):
                self.assertIn(symbol, source)
                self.assertIn(symbol, header)
        self.assertRegex(source, r"extern\s+const\s+int\s+g_intent_golden_sample_count")
        self.assertRegex(source, r"extern\s+const\s+int8_t\s+g_intent_golden_input\[\]")
        self.assertRegex(source, r"extern\s+const\s+int32_t\s+g_intent_golden_expected_indices\[\]")


if __name__ == "__main__":
    unittest.main()
