#!/usr/bin/env python3
"""Benchmark single-class YOLO11 RKNN models on NanoPi M5/RK3576."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

for site in ("/usr/lib/python3/dist-packages", "/usr/local/lib/python3.12/dist-packages"):
    if site not in sys.path:
        sys.path.append(site)

import cv2
from rknnlite.api import RKNNLite


def letterbox(image: np.ndarray, size: int) -> tuple[np.ndarray, float, int, int]:
    height, width = image.shape[:2]
    scale = min(size / width, size / height)
    resized_width = max(1, int(round(width * scale)))
    resized_height = max(1, int(round(height * scale)))
    resized = cv2.resize(image, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR)
    pad_x = (size - resized_width) // 2
    pad_y = (size - resized_height) // 2
    canvas = np.zeros((size, size, 3), dtype=np.uint8)
    canvas[pad_y : pad_y + resized_height, pad_x : pad_x + resized_width] = resized
    return cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB), scale, pad_x, pad_y


def dfl(position: np.ndarray) -> np.ndarray:
    batch, channels, height, width = position.shape
    bins = channels // 4
    values = position.reshape(batch, 4, bins, height, width)
    values = values - values.max(axis=2, keepdims=True)
    probabilities = np.exp(values)
    probabilities /= probabilities.sum(axis=2, keepdims=True)
    return (probabilities * np.arange(bins, dtype=np.float32).reshape(1, 1, bins, 1, 1)).sum(axis=2)


def decode(outputs: list[np.ndarray], size: int, threshold: float) -> list[tuple[list[float], float]]:
    detections: list[tuple[list[float], float]] = []
    for branch in range(3):
        position = outputs[branch * 3]
        confidence = outputs[branch * 3 + 1]
        if confidence.ndim != 4:
            continue
        distances = dfl(position)
        grid_height, grid_width = confidence.shape[2:4]
        stride_x = size / grid_width
        stride_y = size / grid_height
        ys, xs = np.where(confidence[0, 0] >= threshold)
        for y, x in zip(ys.tolist(), xs.tolist()):
            score = float(confidence[0, 0, y, x])
            left, top, right, bottom = distances[0, :, y, x]
            center_x = (x + 0.5) * stride_x
            center_y = (y + 0.5) * stride_y
            box = [
                center_x - float(left) * stride_x,
                center_y - float(top) * stride_y,
                center_x + float(right) * stride_x,
                center_y + float(bottom) * stride_y,
            ]
            detections.append((box, score))
    detections.sort(key=lambda item: item[1], reverse=True)
    return detections


def benchmark(model_path: Path, image: np.ndarray, size: int, runs: int, threshold: float) -> None:
    runtime = RKNNLite(verbose=False)
    if runtime.load_rknn(str(model_path)) != 0:
        raise RuntimeError(f"failed to load {model_path}")
    if runtime.init_runtime() != 0:
        raise RuntimeError(f"failed to initialize NPU for {model_path}")
    input_image, scale, pad_x, pad_y = letterbox(image, size)
    input_batch = input_image[np.newaxis, ...]
    for _ in range(3):
        runtime.inference(inputs=[input_batch], data_format=["nhwc"])
    timings = []
    outputs = None
    for _ in range(runs):
        started = time.perf_counter()
        outputs = runtime.inference(inputs=[input_batch], data_format=["nhwc"])
        timings.append((time.perf_counter() - started) * 1000.0)
    assert outputs is not None
    detections = decode(outputs, size, threshold)
    best = None
    if detections:
        box, score = detections[0]
        best = {
            "confidence": round(score, 4),
            "bbox_xyxy": [round((box[0] - pad_x) / scale, 2), round((box[1] - pad_y) / scale, 2), round((box[2] - pad_x) / scale, 2), round((box[3] - pad_y) / scale, 2)],
        }
    print(
        {
            "model": model_path.name,
            "input_size": size,
            "runs": runs,
            "mean_ms": round(float(np.mean(timings)), 3),
            "p95_ms": round(float(np.percentile(timings, 95)), 3),
            "fps_from_inference": round(1000.0 / float(np.mean(timings)), 2),
            "output_shapes": [list(output.shape) for output in outputs],
            "best": best,
        }
    )
    runtime.release()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="/home/pi/rehab_vla_frames/latest_left.jpg")
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--threshold", type=float, default=0.20)
    parser.add_argument("--model", action="append", nargs=2, metavar=("PATH", "SIZE"), required=True)
    args = parser.parse_args()
    image = cv2.imread(args.image)
    if image is None:
        raise FileNotFoundError(args.image)
    for model_path, size in args.model:
        benchmark(Path(model_path), image, int(size), max(1, args.runs), args.threshold)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
