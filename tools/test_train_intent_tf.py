import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import train_intent_tf as train


class TrainIntentTfTests(unittest.TestCase):
    def test_select_feature_columns_excludes_metadata_non_numeric_empty_and_constant_columns(self):
        df = pd.DataFrame(
            {
                "session_id": ["S01", "S01", "S01"],
                "subject_id": ["S01", "S01", "S01"],
                "trial_id": ["001", "001", "002"],
                "label": ["rest", "rest", "elbow_flex"],
                "window_index": [0, 1, 2],
                "window_start_ms": [0, 100, 200],
                "window_end_ms": [300, 400, 500],
                "sample_count": [13, 14, 15],
                "emg_biceps_rms": [100.0, 120.0, 180.0],
                "stale_count": [0, 1, 0],
                "all_nan": [None, None, None],
                "constant_zero": [0.0, 0.0, 0.0],
                "text_feature": ["low", "mid", "high"],
            }
        )

        columns = train.select_feature_columns(df)

        self.assertEqual(columns, ["sample_count", "emg_biceps_rms", "stale_count"])

    def test_encode_labels_uses_stable_sorted_class_order(self):
        encoded, class_names = train.encode_labels(
            pd.Series(["rest", "elbow_flex", "rest", "shoulder_flex"])
        )

        self.assertEqual(class_names, ["elbow_flex", "rest", "shoulder_flex"])
        self.assertEqual(encoded.tolist(), [1, 0, 1, 2])

    def test_split_by_trial_keeps_trials_disjoint(self):
        df = pd.DataFrame(
            {
                "trial_id": ["t1", "t1", "t2", "t2", "t3", "t3", "t4", "t4", "t5", "t5"],
                "label": ["rest", "rest"] * 5,
                "feature": range(10),
            }
        )

        train_df, val_df, test_df = train.split_dataframe(
            df, group_column="trial_id", val_size=0.2, test_size=0.2, seed=7
        )

        train_trials = set(train_df["trial_id"])
        val_trials = set(val_df["trial_id"])
        test_trials = set(test_df["trial_id"])

        self.assertTrue(train_trials)
        self.assertTrue(val_trials)
        self.assertTrue(test_trials)
        self.assertFalse(train_trials & val_trials)
        self.assertFalse(train_trials & test_trials)
        self.assertFalse(val_trials & test_trials)

    def test_time_limit_callback_has_keras_callback_hooks(self):
        callback = train.TimeLimitCallback(max_seconds=60)

        for hook_name in [
            "on_train_begin",
            "on_train_end",
            "on_epoch_begin",
            "on_epoch_end",
            "on_train_batch_begin",
            "on_train_batch_end",
            "on_test_begin",
            "on_test_end",
            "on_test_batch_begin",
            "on_test_batch_end",
            "on_predict_begin",
            "on_predict_end",
            "on_predict_batch_begin",
            "on_predict_batch_end",
        ]:
            self.assertTrue(hasattr(callback, hook_name), hook_name)


if __name__ == "__main__":
    unittest.main()
