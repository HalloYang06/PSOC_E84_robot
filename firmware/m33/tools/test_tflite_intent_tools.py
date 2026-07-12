import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import eval_tflite_intent as eval_tflite
import export_tflite_c_array as export_c
import export_tflm_golden_samples as golden


class TfliteIntentToolTests(unittest.TestCase):
    def test_quantize_tensor_uses_scale_zero_point_and_clips_int8(self):
        detail = {"dtype": np.int8, "quantization": (0.5, -3)}
        values = np.array([[-10.0, 0.0, 1.0, 100.0]], dtype=np.float32)

        quantized = eval_tflite.quantize_tensor(values, detail)

        np.testing.assert_array_equal(
            quantized,
            np.array([[-23, -3, -1, 127]], dtype=np.int8),
        )

    def test_dequantize_tensor_uses_scale_zero_point_for_uint8(self):
        detail = {"dtype": np.uint8, "quantization": (0.25, 128)}
        values = np.array([[128, 132, 124]], dtype=np.uint8)

        dequantized = eval_tflite.dequantize_tensor(values, detail)

        np.testing.assert_allclose(
            dequantized,
            np.array([[0.0, 1.0, -1.0]], dtype=np.float32),
        )

    def test_format_c_array_uses_stable_symbol_and_hex_bytes(self):
        output = export_c.format_c_array(
            data=bytes([0x00, 0x01, 0xFE, 0xFF]),
            symbol="intent_model_int8_tflite",
            source_name="intent_model_int8.tflite",
        )

        self.assertIn("extern const unsigned char intent_model_int8_tflite[]", output)
        self.assertIn("0x00, 0x01, 0xfe, 0xff", output)
        self.assertIn("extern const unsigned int intent_model_int8_tflite_len = 4;", output)

    def test_select_rows_one_per_class_is_deterministic(self):
        rows = golden.select_rows_one_per_class(
            labels=["rest", "elbow_flex", "rest", "elbow_extend", "elbow_flex"],
            class_names=["elbow_extend", "elbow_flex", "rest"],
        )

        self.assertEqual(rows, [3, 1, 0])

    def test_select_rows_one_per_class_prefers_correct_predictions(self):
        rows = golden.select_rows_one_per_class(
            labels=["rest", "elbow_flex", "rest", "elbow_extend", "elbow_flex"],
            class_names=["elbow_extend", "elbow_flex", "rest"],
            predicted_labels=["elbow_extend", "rest", "rest", "elbow_extend", "elbow_flex"],
        )

        self.assertEqual(rows, [3, 4, 2])

    def test_format_golden_c_arrays_includes_shapes_and_expected_labels(self):
        output = golden.format_golden_c_arrays(
            input_int8=np.array([[1, -2, 3], [4, 5, -6]], dtype=np.int8),
            output_int8=np.array([[-128, 127], [0, 64]], dtype=np.int8),
            expected_indices=np.array([1, 0], dtype=np.int32),
            symbol_prefix="g_intent_golden",
        )

        self.assertIn("extern const int g_intent_golden_sample_count = 2;", output)
        self.assertIn("extern const int g_intent_golden_feature_count = 3;", output)
        self.assertIn("extern const int8_t g_intent_golden_input[]", output)
        self.assertIn("1, -2, 3", output)
        self.assertIn("-128, 127", output)
        self.assertIn("extern const int32_t g_intent_golden_expected_indices[] = {1, 0};", output)


if __name__ == "__main__":
    unittest.main()
