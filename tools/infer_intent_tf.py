import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix

from train_intent_tf import Preprocessor


def preprocessor_from_payload(payload: dict) -> Preprocessor:
    return Preprocessor(
        feature_columns=list(payload["feature_columns"]),
        medians={key: float(value) for key, value in payload["medians"].items()},
        means={key: float(value) for key, value in payload["means"].items()},
        stds={key: float(value) for key, value in payload["stds"].items()},
    )


def decode_predictions(probabilities: np.ndarray, class_names: list[str]) -> list[dict]:
    rows: list[dict] = []
    predicted_indices = probabilities.argmax(axis=1)
    for row_index, predicted_index in enumerate(predicted_indices):
        row = {
            "predicted_index": int(predicted_index),
            "predicted_label": class_names[int(predicted_index)],
            "confidence": float(probabilities[row_index, predicted_index]),
        }
        for class_index, class_name in enumerate(class_names):
            row[f"prob_{class_name}"] = float(probabilities[row_index, class_index])
        rows.append(row)
    return rows


def run_inference(args: argparse.Namespace) -> Path:
    import tensorflow as tf

    model_dir = Path(args.model_dir)
    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else model_dir / "predictions.csv"

    labels_payload = read_json(model_dir / "labels.json")
    preprocess_payload = read_json(model_dir / "preprocess.json")
    class_names = list(labels_payload["class_names"])
    preprocessor = preprocessor_from_payload(preprocess_payload)

    df = pd.read_csv(input_path)
    if args.limit and args.limit > 0:
        df = df.head(args.limit).copy()

    missing = [column for column in preprocessor.feature_columns if column not in df.columns]
    if missing:
        raise ValueError(f"Input CSV is missing trained feature columns: {missing}")

    X = preprocessor.transform(df)
    model = tf.keras.models.load_model(model_dir / "intent_model.keras")
    probabilities = model.predict(X, batch_size=args.batch_size, verbose=args.verbose)
    prediction_rows = decode_predictions(probabilities, class_names)

    metadata_columns = [
        column
        for column in ["session_id", "subject_id", "trial_id", "label", "window_index", "window_start_ms", "window_end_ms"]
        if column in df.columns
    ]
    output_df = pd.concat(
        [
            df[metadata_columns].reset_index(drop=True),
            pd.DataFrame(prediction_rows),
        ],
        axis=1,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_df.to_csv(output_path, index=False, encoding="utf-8")

    metrics = {
        "input_file": str(input_path),
        "model_dir": str(model_dir),
        "output_file": str(output_path),
        "rows": int(len(output_df)),
        "class_names": class_names,
    }
    label_column = preprocess_payload.get("label_column", "label")
    if label_column in df.columns:
        label_to_index = {label: index for index, label in enumerate(class_names)}
        valid_mask = df[label_column].astype(str).isin(label_to_index)
        if valid_mask.any():
            y_true = df.loc[valid_mask, label_column].astype(str).map(label_to_index).to_numpy(dtype=np.int64)
            y_pred = probabilities[valid_mask.to_numpy()].argmax(axis=1)
            metrics["classification_report"] = classification_report(
                y_true,
                y_pred,
                labels=list(range(len(class_names))),
                target_names=class_names,
                output_dict=True,
                zero_division=0,
            )
            metrics["confusion_matrix"] = confusion_matrix(
                y_true, y_pred, labels=list(range(len(class_names)))
            ).tolist()

    write_json(output_path.with_suffix(".metrics.json"), metrics)
    print(f"[infer] model_dir={model_dir}")
    print(f"[infer] input={input_path}")
    print(f"[infer] output={output_path}")
    print(f"[infer] rows={len(output_df)}")
    return output_path


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run TensorFlow inference with a trained intent model.")
    parser.add_argument("--model-dir", required=True, help="Directory containing intent_model.keras, labels.json, preprocess.json.")
    parser.add_argument("--input", required=True, help="Windowed CSV to classify.")
    parser.add_argument("--output", default=None, help="Output predictions CSV. Defaults to <model-dir>/predictions.csv.")
    parser.add_argument("--limit", type=int, default=0, help="Optionally classify only the first N rows.")
    parser.add_argument("--batch-size", type=int, default=256, help="Inference batch size.")
    parser.add_argument("--verbose", type=int, default=0, choices=[0, 1, 2], help="TensorFlow predict verbosity.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    run_inference(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
