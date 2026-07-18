import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from infer_intent_tf import preprocessor_from_payload, read_json


def representative_rows(df: pd.DataFrame, label_column: str, max_rows: int, seed: int) -> pd.DataFrame:
    if max_rows <= 0 or len(df) <= max_rows:
        return df.copy()

    labels = df[label_column].astype(str) if label_column in df.columns else None
    if labels is None:
        return df.sample(n=max_rows, random_state=seed)

    parts = []
    per_class = max(1, max_rows // max(1, labels.nunique()))
    for _, group in df.groupby(labels, sort=True):
        parts.append(group.sample(n=min(len(group), per_class), random_state=seed))
    sampled = pd.concat(parts, ignore_index=False)
    if len(sampled) < max_rows:
        remaining = df.drop(index=sampled.index, errors="ignore")
        if len(remaining) > 0:
            sampled = pd.concat(
                [
                    sampled,
                    remaining.sample(n=min(len(remaining), max_rows - len(sampled)), random_state=seed),
                ],
                ignore_index=False,
            )
    return sampled.sample(frac=1.0, random_state=seed).head(max_rows).copy()


def quantize(args: argparse.Namespace) -> Path:
    import tensorflow as tf

    model_dir = Path(args.model_dir)
    output_path = Path(args.output) if args.output else model_dir / "intent_model_full_int8.tflite"
    metadata_path = output_path.with_suffix(".quantization.json")

    preprocess_payload = read_json(model_dir / "preprocess.json")
    preprocessor = preprocessor_from_payload(preprocess_payload)
    label_column = preprocess_payload.get("label_column", "label")

    df = pd.read_csv(args.input)
    rep_df = representative_rows(df, label_column=label_column, max_rows=args.representative_rows, seed=args.seed)
    rep_x = preprocessor.transform(rep_df)

    def representative_dataset():
        for row in rep_x:
            yield [row.reshape(1, -1).astype(np.float32)]

    converter = tf.lite.TFLiteConverter.from_keras_model(tf.keras.models.load_model(model_dir / "intent_model.keras"))
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.representative_dataset = representative_dataset
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(converter.convert())

    interpreter = tf.lite.Interpreter(model_path=str(output_path))
    interpreter.allocate_tensors()
    input_detail = interpreter.get_input_details()[0]
    output_detail = interpreter.get_output_details()[0]
    ops = []
    if hasattr(interpreter, "_get_ops_details"):
        ops = [op["op_name"] for op in interpreter._get_ops_details()]

    payload = {
        "model_path": str(output_path),
        "model_size_bytes": output_path.stat().st_size,
        "source_model_dir": str(model_dir),
        "input_file": str(args.input),
        "representative_rows": int(len(rep_df)),
        "input_dtype": str(input_detail["dtype"]),
        "input_shape": [int(v) for v in input_detail["shape"].tolist()],
        "input_quantization": list(input_detail.get("quantization", (0.0, 0))),
        "output_dtype": str(output_detail["dtype"]),
        "output_shape": [int(v) for v in output_detail["shape"].tolist()],
        "output_quantization": list(output_detail.get("quantization", (0.0, 0))),
        "ops": ops,
    }
    metadata_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[int8] output={output_path}")
    print(f"[int8] bytes={payload['model_size_bytes']} representative_rows={payload['representative_rows']}")
    print(f"[int8] input={payload['input_dtype']} quant={payload['input_quantization']}")
    print(f"[int8] output_dtype={payload['output_dtype']} quant={payload['output_quantization']}")
    print(f"[int8] metadata={metadata_path}")
    return output_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export a full-int8 TFLite intent model.")
    parser.add_argument("--model-dir", required=True, help="Directory containing intent_model.keras and preprocess.json.")
    parser.add_argument("--input", required=True, help="Windowed CSV used for representative calibration.")
    parser.add_argument("--output", default=None, help="Output .tflite path. Defaults to <model-dir>/intent_model_full_int8.tflite.")
    parser.add_argument("--representative-rows", type=int, default=512, help="Rows used for int8 calibration.")
    parser.add_argument("--seed", type=int, default=42)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    quantize(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
