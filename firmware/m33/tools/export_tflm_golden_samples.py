import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from eval_tflite_intent import dequantize_tensor, quantize_tensor
from infer_intent_tf import preprocessor_from_payload, read_json


def select_rows_one_per_class(
    labels: list[str],
    class_names: list[str],
    predicted_labels: list[str] | None = None,
) -> list[int]:
    selected: list[int] = []
    for class_name in class_names:
        if predicted_labels is not None:
            for index, label in enumerate(labels):
                if label == class_name and predicted_labels[index] == class_name:
                    selected.append(index)
                    break
            if selected and labels[selected[-1]] == class_name:
                continue
        for index, label in enumerate(labels):
            if label == class_name:
                selected.append(index)
                break
    return selected


def run_tflite_raw(model_path: Path, input_float: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    import tensorflow as tf

    interpreter = tf.lite.Interpreter(model_path=str(model_path))
    input_detail = interpreter.get_input_details()[0]
    interpreter.resize_tensor_input(input_detail["index"], input_float.shape, strict=False)
    interpreter.allocate_tensors()
    input_detail = interpreter.get_input_details()[0]
    output_detail = interpreter.get_output_details()[0]

    input_quantized = quantize_tensor(input_float, input_detail)
    interpreter.set_tensor(input_detail["index"], input_quantized)
    interpreter.invoke()
    output_raw = interpreter.get_tensor(output_detail["index"])
    output_float = dequantize_tensor(output_raw, output_detail)

    metadata = {
        "input_dtype": str(input_detail["dtype"]),
        "input_quantization": list(input_detail.get("quantization", (0.0, 0))),
        "output_dtype": str(output_detail["dtype"]),
        "output_quantization": list(output_detail.get("quantization", (0.0, 0))),
    }
    return input_quantized.astype(np.int8), output_raw.astype(np.int8), {
        **metadata,
        "output_float": output_float.astype(np.float32),
    }


def format_golden_c_arrays(
    input_int8: np.ndarray,
    output_int8: np.ndarray,
    expected_indices: np.ndarray,
    symbol_prefix: str,
) -> str:
    sample_count, feature_count = input_int8.shape
    _, class_count = output_int8.shape
    lines = [
        "// Generated TFLite Micro golden samples for the intent model.",
        '#include <cstdint>',
        "",
        f"extern const int {symbol_prefix}_sample_count = {sample_count};",
        f"extern const int {symbol_prefix}_feature_count = {feature_count};",
        f"extern const int {symbol_prefix}_class_count = {class_count};",
        "",
        f"extern const int8_t {symbol_prefix}_input[] = {{",
    ]
    for row in input_int8:
        lines.append("    " + ", ".join(str(int(value)) for value in row) + ",")
    lines.extend(["};", "", f"extern const int8_t {symbol_prefix}_expected_output[] = {{"])
    for row in output_int8:
        lines.append("    " + ", ".join(str(int(value)) for value in row) + ",")
    lines.extend(
        [
            "};",
            "",
            f"extern const int32_t {symbol_prefix}_expected_indices[] = "
            + "{"
            + ", ".join(str(int(value)) for value in expected_indices)
            + "};",
            "",
        ]
    )
    return "\n".join(lines)


def export_golden_samples(args: argparse.Namespace) -> dict:
    model_dir = Path(args.model_dir)
    model_path = Path(args.tflite)
    input_csv = Path(args.input)
    output_dir = Path(args.output_dir) if args.output_dir else model_dir / "tflm_golden"
    output_dir.mkdir(parents=True, exist_ok=True)

    labels_payload = read_json(model_dir / "labels.json")
    preprocess_payload = read_json(model_dir / "preprocess.json")
    class_names = list(labels_payload["class_names"])
    label_column = preprocess_payload.get("label_column", "label")
    preprocessor = preprocessor_from_payload(preprocess_payload)

    df = pd.read_csv(input_csv)
    all_input_float = preprocessor.transform(df)
    _, _, all_metadata = run_tflite_raw(model_path, all_input_float)
    all_output_float = all_metadata["output_float"]
    all_predicted_labels = [class_names[int(index)] for index in all_output_float.argmax(axis=1)]

    selected_indices = select_rows_one_per_class(
        df[label_column].astype(str).tolist(),
        class_names,
        predicted_labels=all_predicted_labels,
    )
    if args.extra_rows > 0:
        for index in range(len(df)):
            if index not in selected_indices:
                selected_indices.append(index)
            if len(selected_indices) >= len(class_names) + args.extra_rows:
                break
    selected_df = df.iloc[selected_indices].copy()

    input_float = preprocessor.transform(selected_df)
    input_int8, output_int8, metadata = run_tflite_raw(model_path, input_float)
    output_float = metadata.pop("output_float")
    expected_indices = output_float.argmax(axis=1).astype(np.int32)

    samples = []
    for row_pos, row_index in enumerate(selected_indices):
        source_row = selected_df.iloc[row_pos]
        samples.append(
            {
                "source_row": int(row_index),
                "trial_id": str(source_row.get("trial_id", "")),
                "true_label": str(source_row.get(label_column, "")),
                "expected_index": int(expected_indices[row_pos]),
                "expected_label": class_names[int(expected_indices[row_pos])],
                "expected_output_int8": [int(value) for value in output_int8[row_pos].tolist()],
                "expected_output_float": [float(value) for value in output_float[row_pos].tolist()],
                "input_int8": [int(value) for value in input_int8[row_pos].tolist()],
            }
        )

    payload = {
        "model_dir": str(model_dir),
        "model_path": str(model_path),
        "input_csv": str(input_csv),
        "class_names": class_names,
        "feature_columns": preprocessor.feature_columns,
        "sample_count": int(len(samples)),
        "feature_count": int(input_int8.shape[1]),
        "class_count": int(output_int8.shape[1]),
        "runtime": metadata,
        "samples": samples,
    }

    json_path = output_dir / "golden_samples.json"
    cc_path = output_dir / "intent_golden_samples.cc"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    cc_path.write_text(
        format_golden_c_arrays(
            input_int8=input_int8,
            output_int8=output_int8,
            expected_indices=expected_indices,
            symbol_prefix=args.symbol_prefix,
        ),
        encoding="utf-8",
        newline="\n",
    )
    print(f"[golden] samples={len(samples)} features={input_int8.shape[1]} classes={output_int8.shape[1]}")
    print(f"[golden] json={json_path}")
    print(f"[golden] cc={cc_path}")
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export fixed int8 input/output golden samples for TFLite Micro smoke tests.")
    parser.add_argument("--model-dir", required=True, help="Directory containing labels.json and preprocess.json.")
    parser.add_argument("--tflite", required=True, help="Full-int8 TFLite model path.")
    parser.add_argument("--input", required=True, help="Windowed CSV source.")
    parser.add_argument("--output-dir", default=None, help="Output directory. Defaults to <model-dir>/tflm_golden.")
    parser.add_argument("--extra-rows", type=int, default=4, help="Extra deterministic rows after one row per class.")
    parser.add_argument("--symbol-prefix", default="g_intent_golden", help="C symbol prefix.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    export_golden_samples(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
