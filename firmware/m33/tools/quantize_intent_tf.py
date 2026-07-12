import argparse
import json
from pathlib import Path

import pandas as pd

from infer_intent_tf import preprocessor_from_payload, read_json


def representative_dataset(input_csv: Path, preprocess_payload: dict, limit: int):
    preprocessor = preprocessor_from_payload(preprocess_payload)
    df = pd.read_csv(input_csv)
    if limit > 0:
        df = df.head(limit).copy()
    X = preprocessor.transform(df)
    for row in X:
        yield [row.reshape(1, -1).astype("float32")]


def export_tflite_models(args: argparse.Namespace) -> dict:
    import tensorflow as tf

    model_dir = Path(args.model_dir)
    input_csv = Path(args.input)
    output_dir = Path(args.output_dir) if args.output_dir else model_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    model = tf.keras.models.load_model(model_dir / "intent_model.keras")
    preprocess_payload = read_json(model_dir / "preprocess.json")

    float32_converter = tf.lite.TFLiteConverter.from_keras_model(model)
    float32_model = float32_converter.convert()
    float32_path = output_dir / "intent_model_float32.tflite"
    float32_path.write_bytes(float32_model)

    int8_converter = tf.lite.TFLiteConverter.from_keras_model(model)
    int8_converter.optimizations = [tf.lite.Optimize.DEFAULT]
    int8_converter.representative_dataset = lambda: representative_dataset(
        input_csv=input_csv,
        preprocess_payload=preprocess_payload,
        limit=args.representative_limit,
    )
    int8_converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    int8_converter.inference_input_type = tf.int8
    int8_converter.inference_output_type = tf.int8
    int8_model = int8_converter.convert()
    int8_path = output_dir / "intent_model_int8.tflite"
    int8_path.write_bytes(int8_model)

    report = {
        "model_dir": str(model_dir),
        "input_csv": str(input_csv),
        "representative_limit": int(args.representative_limit),
        "float32_path": str(float32_path),
        "float32_size_bytes": len(float32_model),
        "int8_path": str(int8_path),
        "int8_size_bytes": len(int8_model),
    }
    report_path = output_dir / "quantization_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[quantize] float32={float32_path} size={len(float32_model)}")
    print(f"[quantize] int8={int8_path} size={len(int8_model)}")
    print(f"[quantize] report={report_path}")
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export float32 and full-int8 TFLite models for the intent classifier.")
    parser.add_argument("--model-dir", required=True, help="Directory containing intent_model.keras and preprocess.json.")
    parser.add_argument("--input", required=True, help="Windowed CSV used as the representative dataset source.")
    parser.add_argument("--output-dir", default=None, help="Output directory. Defaults to --model-dir.")
    parser.add_argument("--representative-limit", type=int, default=512, help="Rows to use for int8 representative dataset.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    export_tflite_models(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
