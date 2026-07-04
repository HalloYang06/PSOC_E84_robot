import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import infer_intent_tf as infer


class InferIntentTfTests(unittest.TestCase):
    def test_preprocessor_from_payload_transforms_columns_in_training_order(self):
        payload = {
            "feature_columns": ["b", "a"],
            "medians": {"a": 10.0, "b": 20.0},
            "means": {"a": 11.0, "b": 22.0},
            "stds": {"a": 2.0, "b": 4.0},
        }
        df = pd.DataFrame({"a": [13.0], "b": [30.0]})

        preprocessor = infer.preprocessor_from_payload(payload)
        transformed = preprocessor.transform(df)

        np.testing.assert_allclose(transformed, np.array([[2.0, 1.0]], dtype=np.float32))

    def test_decode_predictions_returns_label_confidence_and_probabilities(self):
        probabilities = np.array([[0.1, 0.7, 0.2], [0.6, 0.3, 0.1]], dtype=np.float32)
        class_names = ["elbow_extend", "elbow_flex", "rest"]

        rows = infer.decode_predictions(probabilities, class_names)

        self.assertEqual(rows[0]["predicted_label"], "elbow_flex")
        self.assertAlmostEqual(rows[0]["confidence"], 0.7, places=6)
        self.assertAlmostEqual(rows[0]["prob_rest"], 0.2, places=6)
        self.assertEqual(rows[1]["predicted_label"], "elbow_extend")
        self.assertAlmostEqual(rows[1]["prob_elbow_flex"], 0.3, places=6)


if __name__ == "__main__":
    unittest.main()
