import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

from infer_intent_tf import decode_predictions, preprocessor_from_payload, read_json
from train_intent_tf import split_dataframe


def quantize_tensor(values: np.ndarray, detail: dict) -> np.ndarray:
    dtype = detail["dtype"]
    if np.issubdtype(dtype, np.floating):
        return values.astype(dtype)
    scale, zero_point = detail.get("quantization", (0.0, 0))
    if not scale:
        return values.astype(dtype)
    quantized = np.round(values / scale + zero_point)
    info = np.iinfo(dtype)
    quantized = np.clip(quantized, info.min, info.max)
    return quantized.astype(dtype)


def dequantize_tensor(values: np.ndarray, detail: dict) -> np.ndarray:
    dtype = detail["dtype"]
    if np.issubdtype(dtype, np.floating):
        return values.astype(np.float32)
    scale, zero_point = detail.get("quantization", (0.0, 0))
    if not scale:
        return values.astype(np.float32)
    return ((values.astype(np.float32) - zero_point) * scale).astype(np.float32)


def run_tflite_model(model_path: Path, X: np.ndarray, batch_size: int) -> tuple[np.ndarray, dict]:
    import tensorflow as tf

    interpreter = tf.lite.Interpreter(model_path=str(model_path))
    all_outputs: list[np.ndarray] = []
    started_at = time.time()

    for start in range(0, len(X), batch_size):
        batch = X[start : start + batch_size]
        input_detail = interpreter.get_input_details()[0]
        interpreter.resize_tensor_input(input_detail["index"], batch.shape, strict=False)
        interpreter.allocate_tensors()
        input_detail = interpreter.get_input_details()[0]
        output_detail = interpreter.get_output_details()[0]
        interpreter.set_tensor(input_detail["index"], quantize_tensor(batch, input_detail))
        interpreter.invoke()
        raw_output = interpreter.get_tensor(output_detail["index"])
        all_outputs.append(dequantize_tensor(raw_output, output_detail))

    elapsed = time.time() - started_at
    input_detail = interpreter.get_input_details()[0]
    output_detail = interpreter.get_output_details()[0]
    ops = []
    if hasattr(interpreter, "_get_ops_details"):
        ops = [op["op_name"] for op in interpreter._get_ops_details()]
    metadata = {
        "input_dtype": str(input_detail["dtype"]),
        "input_quantization": list(input_detail.get("quantization", (0.0, 0))),
        "output_dtype": str(output_detail["dtype"]),
        "output_quantization": list(output_detail.get("quantization", (0.0, 0))),
        "elapsed_seconds": round(elapsed, 6),
        "rows_per_second": round(float(len(X) / elapsed), 3) if elapsed > 0 else None,
        "ops": ops,
    }
    return np.vstack(all_outputs), metadata


def evaluate_tflite(args: argparse.Namespace) -> Path:
    model_dir = Path(args.model_dir)
    model_path = Path(args.tflite)
    output_dir = Path(args.output_dir) if args.output_dir else model_dir / "tflite_eval"
    output_dir.mkdir(parents=True, exist_ok=True)
    name = args.name or model_path.stem

    labels_payload = read_json(model_dir / "labels.json")
    preprocess_payload = read_json(model_dir / "preprocess.json")
    class_names = list(labels_payload["class_names"])
    label_to_index = {label: index for index, label in enumerate(class_names)}
    preprocessor = preprocessor_from_payload(preprocess_payload)

    df = pd.read_csv(args.input)
    label_column = preprocess_payload.get("label_column", "label")
    if not args.all_rows:
        _, _, df = split_dataframe(
            df,
            group_column=preprocess_payload.get("group_column", "trial_id"),
            val_size=args.val_size,
            test_size=args.test_size,
            seed=args.seed,
            label_column=label_column,
        )
    df = df[df[label_column].astype(str).isin(label_to_index)].copy()

    X = preprocessor.transform(df)
    probabilities, runtime_metadata = run_tflite_model(model_path, X, batch_size=args.batch_size)
    y_true = df[label_column].astype(str).map(label_to_index).to_numpy(dtype=np.int64)
    y_pred = probabilities.argmax(axis=1)

    report = classification_report(
        y_true,
        y_pred,
        labels=list(range(len(class_names))),
        target_names=class_names,
        output_dict=True,
        zero_division=0,
    )
    matrix = confusion_matrix(y_true, y_pred, labels=list(range(len(class_names)))
)
    predictions = pd.concat(
        [
            df[[column for column in ["session_id", "subject_id", "trial_id", label_column, "window_index"] if column in df.columns]]
            .reset_index(drop=True),
            pd.DataFrame(decode_predictions(probabilities, class_names)),
        ],
        axis=1,
    )

    predictions_path = output_dir / f"{name}_predictions.csv"
    metrics_path = output_dir / f"{name}_metrics.json"
    confusion_path = output_dir / f"{name}_confusion_matrix.csv"
    predictions.to_csv(predictions_path, index=False, encoding="utf-8")
    pd.DataFrame(matrix, index=class_names, columns=class_names).to_csv(confusion_path)

    metrics = {
        "name": name,
        "model_path": str(model_path),
        "model_size_bytes": model_path.stat().st_size,
        "input_file": str(args.input),
        "rows": int(len(df)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "classification_report": report,
        "confusion_matrix": matrix.tolist(),
        "runtime": runtime_metadata,
        "predictions_path": str(predictions_path),
        "confusion_matrix_path": str(confusion_path),
    }
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[eval] name={name}")
    print(f"[eval] rows={len(df)} accuracy={metrics['accuracy']:.4f}")
    print(f"[eval] size={metrics['model_size_bytes']} bytes ops={runtime_metadata['ops']}")
    print(f"[eval] metrics={metrics_path}")
    return metrics_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate a TFLite intent model on the PC.")
    parser.add_argument("--model-dir", required=True, help="Directory containing labels.json and preprocess.json.")
    parser.add_argument("--tflite", required=True, help="TFLite model path.")
    parser.add_argument("--input", required=True, help="Windowed CSV to evaluate.")
    parser.add_argument("--output-dir", default=None, help="Output directory. Defaults to <model-dir>/tflite_eval.")
    parser.add_argument("--name", default=None, help="Name prefix for output files.")
    parser.add_argument("--batch-size", type=int, default=256, help="PC-side evaluation batch size.")
    parser.add_argument("--all-rows", action="store_true", help="Evaluate all rows instead of reproducing the test split.")
    parser.add_argument("--val-size", type=float, default=0.15, help="Validation fraction used by the original training split.")
    parser.add_argument("--test-size", type=float, default=0.15, help="Test fraction used by the original training split.")
    parser.add_argument("--seed", type=int, default=42, help="Seed used by the original training split.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    evaluate_tflite(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
