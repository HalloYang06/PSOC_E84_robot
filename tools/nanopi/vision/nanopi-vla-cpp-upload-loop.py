#!/usr/bin/env python3
"""
Upload VLA vision evidence produced by the C++ pixel-servo probe.

The C++ probe owns camera capture and fast OpenCV target detection. This Python
wrapper only uploads the latest annotated frames and context to the platform.
It never sends motor or CAN commands.
"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import os
import shutil
import subprocess
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
import urllib.request
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import requests

try:
    import onnxruntime as ort
except Exception:  # pragma: no cover - system Python may not see the venv yet
    import sys
    for _site in (
        "/home/pi/rehab_vla/venv/lib/python3.12/site-packages",
        "/home/pi/rehab_vla/venv/local/lib/python3.12/dist-packages",
        "/home/pi/rehab_vla/venv/lib/python3/dist-packages",
        "/home/pi/rehab_vla/venv/lib/python3.12/dist-packages",
    ):
        if _site not in sys.path:
            sys.path.append(_site)
    try:
        import onnxruntime as ort
    except Exception:
        ort = None

try:
    from rknnlite.api import RKNNLite
    from nanopi_vla_rknn_benchmark import decode as decode_rknn_yolo11
    from nanopi_vla_rknn_benchmark import letterbox as letterbox_rknn
except Exception:
    RKNNLite = None
    decode_rknn_yolo11 = None
    letterbox_rknn = None


CONTROL_BOUNDARY = "stereo_vision_context_only_not_motion_permission"
EFF_HISTORY = deque(maxlen=5)
VISUAL_LOCK_HISTORY = deque(maxlen=5)
POINT_STEREO_DEPTH_HISTORY = deque(maxlen=8)
TARGET_TRACKERS: dict[str, dict[str, Any]] = {"left": {}, "right": {}}
LATEST_ORT_PAYLOAD: dict[str, Any] | None = None
LATEST_ORT_FRAME_INDEX = 0
LATEST_RIGHT_TARGET_RESULT: tuple[dict[str, Any] | None, dict[str, Any], list[dict[str, Any]]] | None = None
LATEST_RIGHT_TARGET_FRAME_INDEX = 0
CAPTURE_DAEMON_PROC: subprocess.Popen[str] | None = None
CAPTURE_DAEMON_LAST_INDEX = 0
HEAVY_EXECUTOR = ThreadPoolExecutor(max_workers=1)
DETECTION_EXECUTOR = ThreadPoolExecutor(max_workers=3)
UPLOAD_EXECUTOR = ThreadPoolExecutor(max_workers=1)
TARGET_ORT_SESSIONS: dict[str, Any] = {}
TARGET_ORT_IO: dict[str, tuple[str, str]] = {}
RKNN_SESSIONS: dict[str, Any] = {}
FAST_TRACK_STATES: dict[str, dict[str, Any]] = {"target": {}, "end_effector": {}}
STEREO_RECTIFY_MAP_CACHE: dict[tuple[str, int, int], tuple[Any, Any]] = {}
COCO_TARGET_CLASSES = {39: ("target_bottle", "bottle"), 41: ("target_cup", "cup")}
PROJECT_SINGLE_CLASS_CHANNELS = {5, 6}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload C++ VLA probe output to the rehab-arm platform.")
    parser.add_argument("--api-base", default=os.environ.get("REHAB_API_BASE", "http://127.0.0.1:8010"))
    parser.add_argument("--project-id", default=os.environ.get("REHAB_PROJECT_ID", "proj_rehab_arm"))
    parser.add_argument("--device-id", default=os.environ.get("REHAB_DEVICE_ID", "nanopi-m5"))
    parser.add_argument("--robot-id", default=os.environ.get("REHAB_ROBOT_ID", "rehab-arm-alpha"))
    parser.add_argument("--left", default=os.environ.get("REHAB_LEFT_CAMERA", "/dev/video45"))
    parser.add_argument("--right", default=os.environ.get("REHAB_RIGHT_CAMERA", "/dev/video47"))
    parser.add_argument("--left-flip", default=os.environ.get("REHAB_LEFT_FLIP", "none"), choices=["none", "h", "v", "hv"])
    parser.add_argument("--right-flip", default=os.environ.get("REHAB_RIGHT_FLIP", os.environ.get("REHAB_LEFT_FLIP", "none")), choices=["none", "h", "v", "hv"])
    parser.add_argument("--probe-bin", default=os.environ.get("REHAB_VLA_CPP_PROBE", "/home/pi/rehab_vla/nanopi_vla_pixel_servo_probe"))
    parser.add_argument("--out-dir", default=os.environ.get("REHAB_VLA_OUT_DIR", "/home/pi/rehab_vla_cpp_probe"))
    parser.add_argument("--target-model", default=os.environ.get("REHAB_TARGET_ONNX", "/home/pi/rehab_arm_models/yolo/yolov5n.onnx"))
    parser.add_argument("--target-conf", type=float, default=float(os.environ.get("REHAB_TARGET_CONF", "0.30")))
    parser.add_argument("--target-imgsz", type=int, default=int(os.environ.get("REHAB_TARGET_IMGSZ", "640")))
    parser.add_argument("--stereo-calibration-json", default=os.environ.get("REHAB_STEREO_CALIBRATION_JSON", "/home/pi/rehab_arm_stereo_calibration/calibrations/chessboard_real_20260703_01_A4_20mm_9x6.json"))
    parser.add_argument("--hard-negative-dir", default=os.environ.get("REHAB_HARD_NEGATIVE_DIR", "/home/pi/rehab_vla_hard_negatives"))
    parser.add_argument("--end-effector-conf", type=float, default=float(os.environ.get("REHAB_END_EFFECTOR_CONF", "0.20")))
    parser.add_argument("--fps", type=float, default=float(os.environ.get("REHAB_VLA_FPS", "1")))
    parser.add_argument("--heavy-every", type=int, default=int(os.environ.get("REHAB_VLA_HEAVY_EVERY", "1")))
    parser.add_argument("--right-upload-every", type=int, default=int(os.environ.get("REHAB_VLA_RIGHT_UPLOAD_EVERY", "1")))
    parser.add_argument("--visual-memory-ttl", type=float, default=float(os.environ.get("REHAB_VISUAL_MEMORY_TTL", "0.8")))
    parser.add_argument("--visual-memory-max-misses", type=int, default=int(os.environ.get("REHAB_VISUAL_MEMORY_MAX_MISSES", "4")))
    parser.add_argument("--visual-ema-alpha", type=float, default=float(os.environ.get("REHAB_VISUAL_EMA_ALPHA", "0.45")))
    parser.add_argument("--capture-daemon-bin", default=os.environ.get("REHAB_VLA_CAPTURE_DAEMON_BIN", "/home/pi/rehab_vla/nanopi_vla_capture_daemon"))
    parser.add_argument("--capture-daemon", action="store_true", default=os.environ.get("REHAB_VLA_CAPTURE_DAEMON", "0") == "1")
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--no-upload", action="store_true")
    return parser.parse_args()


def post_json(url: str, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=8) as response:
        response.read()


def upload_keyframe(api_base: str, device_id: str, fields: dict[str, Any], image_bytes: bytes, file_name: str) -> None:
    url = f"{api_base.rstrip('/')}/api/rehab-arm/v1/devices/{device_id}/camera/keyframes"
    max_attempts = 4
    request_timeout = (
        float(os.environ.get("REHAB_UPLOAD_CONNECT_TIMEOUT_S", "2.0")),
        float(os.environ.get("REHAB_UPLOAD_READ_TIMEOUT_S", "4.0")),
    )
    for attempt in range(max_attempts):
        response = requests.post(
            url,
            data={key: str(value) for key, value in fields.items()},
            files={"file": (file_name, image_bytes, "image/jpeg")},
            timeout=request_timeout,
        )
        if response.ok:
            return
        detail = response.text[:800]
        if attempt + 1 < max_attempts and response.status_code == 422 and "file field is required" in detail:
            time.sleep(0.02 * (attempt + 1))
            continue
        raise RuntimeError(
            f"keyframe upload failed status={response.status_code} camera={fields.get('camera_id')} detail={detail}"
        )


def _read_probe_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def read_complete_jpeg_bytes(path: Path, retries: int = 4, delay_s: float = 0.004) -> bytes:
    for attempt in range(retries):
        try:
            payload = path.read_bytes()
        except OSError:
            payload = b""
        if len(payload) >= 4 and payload[:2] == b"\xff\xd8" and payload[-2:] == b"\xff\xd9":
            return payload
        if attempt + 1 < retries:
            time.sleep(delay_s)
    raise RuntimeError(f"incomplete JPEG after {retries} reads: {path}")


def read_complete_jpeg_image(path: Path, flags: int = cv2.IMREAD_COLOR) -> Any:
    payload = read_complete_jpeg_bytes(path)
    frame = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), flags)
    if frame is None:
        raise RuntimeError(f"JPEG decode failed: {path}")
    return frame


def _stop_capture_daemon() -> None:
    global CAPTURE_DAEMON_PROC
    proc = CAPTURE_DAEMON_PROC
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)


atexit.register(_stop_capture_daemon)
atexit.register(lambda: HEAVY_EXECUTOR.shutdown(wait=False, cancel_futures=True))
atexit.register(lambda: DETECTION_EXECUTOR.shutdown(wait=False, cancel_futures=True))
atexit.register(lambda: UPLOAD_EXECUTOR.shutdown(wait=False, cancel_futures=True))


def run_capture_daemon_probe(args: argparse.Namespace) -> dict[str, Any]:
    global CAPTURE_DAEMON_PROC, CAPTURE_DAEMON_LAST_INDEX
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if CAPTURE_DAEMON_PROC is None or CAPTURE_DAEMON_PROC.poll() is not None:
        context_path = out_dir / "latest_context.json"
        context_path.unlink(missing_ok=True)
        CAPTURE_DAEMON_PROC = subprocess.Popen(
            [
                args.capture_daemon_bin,
                args.left,
                args.right,
                str(out_dir),
                args.left_flip,
                args.right_flip,
                str(max(args.fps, 0.1)),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        CAPTURE_DAEMON_LAST_INDEX = 0

    context_path = out_dir / "latest_context.json"
    deadline = time.time() + 2.0
    latest: dict[str, Any] | None = None
    while time.time() < deadline:
        latest = _read_probe_json(context_path)
        if latest is not None:
            index = int(latest.get("capture_daemon_frame_index") or 0)
            if index > CAPTURE_DAEMON_LAST_INDEX:
                CAPTURE_DAEMON_LAST_INDEX = index
                return latest
        time.sleep(0.02)
    if latest is not None:
        return latest
    raise RuntimeError("capture daemon did not produce latest_context.json")


def run_probe(args: argparse.Namespace) -> dict[str, Any]:
    if args.capture_daemon:
        return run_capture_daemon_probe(args)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run([args.probe_bin, args.left, args.right, str(out_dir), args.left_flip, args.right_flip], check=True, timeout=8)
    return json.loads((out_dir / "latest_context.json").read_text(encoding="utf-8"))


def run_ort_infer(args: argparse.Namespace) -> dict[str, Any]:
    if os.environ.get("REHAB_VLA_RKNN", "0") == "1":
        model_path = os.environ.get(
            "REHAB_END_EFFECTOR_RKNN",
            "/home/pi/rehab_vla/rknn_models/gripper_yolo11n_416_rk3576_int8.rknn",
        )
        return _detect_rknn_single_class(
            Path(args.out_dir) / "latest_left.jpg",
            model_path,
            int(os.environ.get("REHAB_END_EFFECTOR_IMGSZ", "416")),
            args.end_effector_conf,
            os.environ.get("REHAB_END_EFFECTOR_SINGLE_CLASS_LABEL", "gripper_tip"),
            "gripper_left",
        )
    out_dir = Path(args.out_dir)
    cpp_payload = _read_probe_json(out_dir / "latest_ort_context.json")
    if cpp_payload is not None and os.environ.get("REHAB_VLA_CPP_GRIPPER_DNN", os.environ.get("REHAB_VLA_CPP_DNN", "0")) == "1":
        return cpp_payload
    env = os.environ.copy()
    env["REHAB_VLA_OUT_DIR"] = args.out_dir
    env["REHAB_END_EFFECTOR_CONF"] = str(args.end_effector_conf)
    env["REHAB_END_EFFECTOR_FRAME_WIDTH"] = "640"
    env["REHAB_END_EFFECTOR_FRAME_HEIGHT"] = "480"
    env["REHAB_END_EFFECTOR_IMGSZ"] = "416"
    proc = subprocess.run(
        ["/home/pi/rehab_vla/venv/bin/python", "/home/pi/rehab_vla/nanopi_vla_ort_infer.py"],
        check=True,
        timeout=10,
        capture_output=True,
        text=True,
        env=env,
    )
    payload = json.loads(proc.stdout)
    _write_json_atomic(out_dir / "latest_ort_context.json", payload)
    return payload


def _get_rknn_session(model_path: str, session_key: str) -> Any:
    if RKNNLite is None:
        raise RuntimeError("rknn-toolkit-lite2 is not available")
    key = f"{session_key}:{model_path}"
    runtime = RKNN_SESSIONS.get(key)
    if runtime is None:
        runtime = RKNNLite(verbose=False)
        if runtime.load_rknn(model_path) != 0:
            raise RuntimeError(f"failed to load RKNN model: {model_path}")
        if runtime.init_runtime() != 0:
            raise RuntimeError(f"failed to initialize RKNN runtime: {model_path}")
        RKNN_SESSIONS[key] = runtime
        print(f"[cpp-upload] rknn_session_cached key={session_key} model={model_path}")
    return runtime


def _detect_rknn_single_class(
    image_path: Path,
    model_path: str,
    imgsz: int,
    confidence: float,
    label: str,
    session_key: str,
) -> dict[str, Any]:
    frame = read_complete_jpeg_image(image_path)
    if frame is None:
        return {"detections": [], "quality_gate": {"state": "missing_frame", "image_path": str(image_path)}}
    started = time.perf_counter()
    use_letterbox = os.environ.get("REHAB_RKNN_LETTERBOX", "0") == "1"
    if use_letterbox:
        input_image, scale, pad_x, pad_y = letterbox_rknn(frame, imgsz)
        scale_x = scale_y = scale
    else:
        input_image = cv2.cvtColor(cv2.resize(frame, (imgsz, imgsz)), cv2.COLOR_BGR2RGB)
        scale_x = imgsz / float(frame.shape[1])
        scale_y = imgsz / float(frame.shape[0])
        pad_x = pad_y = 0
    runtime = _get_rknn_session(model_path, session_key)
    inference_started = time.perf_counter()
    outputs = runtime.inference(inputs=[input_image[np.newaxis, ...]], data_format=["nhwc"])
    inference_ms = (time.perf_counter() - inference_started) * 1000.0
    if not isinstance(outputs, list):
        raise RuntimeError("RKNN inference returned no outputs")
    decoded = decode_rknn_yolo11(outputs, imgsz, confidence)
    candidates: list[dict[str, Any]] = []
    frame_h, frame_w = frame.shape[:2]
    for box, score in decoded:
        x1 = max(0.0, min(float(frame_w - 1), (float(box[0]) - pad_x) / scale_x))
        y1 = max(0.0, min(float(frame_h - 1), (float(box[1]) - pad_y) / scale_y))
        x2 = max(x1 + 1.0, min(float(frame_w), (float(box[2]) - pad_x) / scale_x))
        y2 = max(y1 + 1.0, min(float(frame_h), (float(box[3]) - pad_y) / scale_y))
        candidates.append(
            {
                "label": label,
                "confidence": round(float(score), 4),
                "bbox_xywh": [round(x1, 2), round(y1, 2), round(x2 - x1, 2), round(y2 - y1, 2)],
                "center_px": [round((x1 + x2) / 2.0, 2), round((y1 + y2) / 2.0, 2)],
                "source": "rk3576_npu_yolo11_int8",
                "model_path": model_path,
            }
        )
    detections = _nms_items(candidates)
    detections.sort(key=lambda item: float(item.get("confidence", 0.0)), reverse=True)
    return {
        "detections": detections[:8],
        "target": detections[0] if detections else None,
        "accepted_candidates": detections[:8],
        "quality_gate": {
            "schema_version": "rknn_detection_quality_gate_v1",
            "state": "candidate_accepted" if detections else "no_candidate_above_threshold",
            "runtime": "rk3576_npu_rknn_toolkit_lite2",
            "model_path": model_path,
            "input_size": imgsz,
            "preprocess": "letterbox_black" if use_letterbox else "direct_resize_legacy_compatible",
            "min_confidence": confidence,
            "inference_ms": round(inference_ms, 3),
            "total_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "control_boundary": "npu_detection_evidence_only_not_motion_permission",
        },
    }


def _nms_items(items: list[dict[str, Any]], iou_threshold: float = 0.45) -> list[dict[str, Any]]:
    if not items:
        return []
    boxes = []
    scores = []
    for item in items:
        bbox = _bbox_xywh(item) or [0.0, 0.0, 0.0, 0.0]
        boxes.append([int(round(v)) for v in bbox])
        scores.append(float(item.get("confidence", 0.0)))
    indices = cv2.dnn.NMSBoxes(boxes, scores, 0.0, iou_threshold)
    flat = np.array(indices).reshape(-1).tolist() if len(indices) else []
    return [items[index] for index in flat]


def _get_target_ort_session(model_path: str) -> tuple[Any, str, str]:
    if ort is None:
        raise RuntimeError("onnxruntime is not available in the VLA upload process")
    key = str(model_path)
    session = TARGET_ORT_SESSIONS.get(key)
    io_names = TARGET_ORT_IO.get(key)
    if session is None or io_names is None:
        options = ort.SessionOptions()
        # Keep capture/upload responsive on NanoPi. Full CPU fan-out makes the
        # detector look fast in isolation but stalls the live VLA loop.
        options.intra_op_num_threads = int(os.environ.get("REHAB_TARGET_ORT_THREADS", "2"))
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(key, sess_options=options, providers=["CPUExecutionProvider"])
        io_names = (session.get_inputs()[0].name, session.get_outputs()[0].name)
        TARGET_ORT_SESSIONS[key] = session
        TARGET_ORT_IO[key] = io_names
        print(f"[cpp-upload] target_ort_session_cached model={key} threads={options.intra_op_num_threads}")
    return session, io_names[0], io_names[1]


def _detect_target_tensor_cached(
    tensor: np.ndarray,
    model_path: str,
    conf: float,
    imgsz: int,
    frame_w: int,
    frame_h: int,
) -> dict[str, Any]:
    min_width = float(os.environ.get("REHAB_TARGET_MIN_WIDTH_PX", "40"))
    min_height = float(os.environ.get("REHAB_TARGET_MIN_HEIGHT_PX", "50"))
    single_class_label = os.environ.get("REHAB_TARGET_SINGLE_CLASS_LABEL", "").strip()
    quality_detector = "project_single_class_target_detector" if single_class_label else "pretrained_yolo_coco_target_detector"
    model = Path(model_path)
    if not model.is_file():
        return {
            "target": None,
            "accepted_candidates": [],
            "quality_gate": {
                "schema_version": "target_quality_gate_v2",
                "state": "target_model_missing",
                "model_path": str(model),
                "detector": quality_detector,
                "control_boundary": "target_quality_gate_only_not_motion_permission",
            },
        }
    session, input_name, output_name = _get_target_ort_session(str(model))
    output = session.run([output_name], {input_name: tensor})[0]
    raw = np.squeeze(np.asarray(output))
    if raw.ndim != 2:
        return {
            "target": None,
            "accepted_candidates": [],
            "quality_gate": {
                "schema_version": "target_quality_gate_v2",
                "state": "unexpected_yolo_output",
                "output_shape": list(np.asarray(output).shape),
                "detector": quality_detector,
                "control_boundary": "target_quality_gate_only_not_motion_permission",
            },
        }
    if raw.shape[0] in {84, 85, *PROJECT_SINGLE_CLASS_CHANNELS} and raw.shape[1] > raw.shape[0]:
        raw = raw.T
    scale_x = frame_w / float(imgsz)
    scale_y = frame_h / float(imgsz)
    candidates: list[dict[str, Any]] = []
    rejected_low_conf = 0
    rejected_too_small = 0
    detector_family = "pretrained_yolo_coco_target_detector"
    for row in raw:
        if len(row) in PROJECT_SINGLE_CLASS_CHANNELS:
            confidence = float(row[4])
            label = os.environ.get("REHAB_TARGET_SINGLE_CLASS_LABEL", "target_bottle")
            coco_label = os.environ.get("REHAB_TARGET_SINGLE_CLASS_COCO_LABEL", "project_custom")
            detector_family = "project_single_class_target_detector"
        elif len(row) < 84:
            continue
        else:
            if len(row) >= 85:
                obj_conf = float(row[4])
                scores = row[5:85]
                detector_family = "yolov5_coco_target_detector"
            else:
                obj_conf = 1.0
                scores = row[4:84]
                detector_family = "yolov8_or_yolo11_coco_target_detector"
            class_id = int(np.argmax(scores))
            if class_id not in COCO_TARGET_CLASSES:
                continue
            confidence = obj_conf * float(scores[class_id])
            label, coco_label = COCO_TARGET_CLASSES[class_id]
        if confidence < conf:
            rejected_low_conf += 1
            continue
        cx, cy, bw, bh = [float(value) for value in row[:4]]
        x = max(0.0, min(float(frame_w - 1), (cx - bw / 2.0) * scale_x))
        y = max(0.0, min(float(frame_h - 1), (cy - bh / 2.0) * scale_y))
        width = max(1.0, min(float(frame_w) - x, bw * scale_x))
        height = max(1.0, min(float(frame_h) - y, bh * scale_y))
        if width < min_width or height < min_height:
            rejected_too_small += 1
            continue
        candidates.append(
            {
                "label": label,
                "coco_label": coco_label,
                "confidence": round(confidence, 4),
                "bbox_xywh": [round(x, 2), round(y, 2), round(width, 2), round(height, 2)],
                "center_px": [round(x + width / 2.0, 2), round(y + height / 2.0, 2)],
                "source": detector_family,
                "model_path": str(model),
            }
        )
    accepted = _nms_items(candidates)
    accepted.sort(key=lambda item: float(item.get("confidence", 0.0)), reverse=True)
    target = accepted[0] if accepted else None
    return {
        "target": target,
        "accepted_candidates": accepted[:8],
        "quality_gate": {
            "schema_version": "target_quality_gate_v2",
            "state": "candidate_accepted" if target else "no_yolo_cup_or_bottle",
            "detector": quality_detector,
            "runtime": "cached_onnxruntime_in_upload_process",
            "model_path": str(model),
            "accepted_count": len(accepted),
            "candidate_count": len(candidates),
            "rejected_low_confidence": rejected_low_conf,
            "rejected_too_small": rejected_too_small,
            "min_confidence": conf,
            "min_size_px": [min_width, min_height],
            "target_classes": ["target_bottle", "target_cup"],
            "control_boundary": "target_quality_gate_only_not_motion_permission",
        },
    }


def detect_target_yolo(args: argparse.Namespace, side: str = "left") -> tuple[dict[str, Any] | None, dict[str, Any], list[dict[str, Any]]]:
    out_dir = Path(args.out_dir)
    context_name = "latest_target_context_right.json" if side == "right" else "latest_target_context.json"
    cpp_payload = _read_probe_json(out_dir / context_name)
    if cpp_payload is not None and os.environ.get("REHAB_VLA_CPP_TARGET_DNN", os.environ.get("REHAB_VLA_CPP_DNN", "0")) == "1":
        target = cpp_payload.get("target") if isinstance(cpp_payload.get("target"), dict) else None
        gate = cpp_payload.get("quality_gate") if isinstance(cpp_payload.get("quality_gate"), dict) else {}
        if gate.get("state") not in {"target_model_missing", "opencv_dnn_model_load_error", "detector_not_run"}:
            return target, gate, [target] if target else []
    frame_name = "latest_right.jpg" if side == "right" else "latest_left.jpg"
    frame_path = out_dir / frame_name
    if os.environ.get("REHAB_VLA_RKNN", "0") == "1":
        model_path = os.environ.get(
            "REHAB_TARGET_RKNN",
            "/home/pi/rehab_vla/rknn_models/target_baisuishan_yolo11n_320_rk3576_int8.rknn",
        )
        payload = _detect_rknn_single_class(
            frame_path,
            model_path,
            args.target_imgsz,
            args.target_conf,
            os.environ.get("REHAB_TARGET_SINGLE_CLASS_LABEL", "target_bottle"),
            f"target_{side}",
        )
        min_width = float(os.environ.get("REHAB_TARGET_MIN_WIDTH_PX", "40"))
        min_height = float(os.environ.get("REHAB_TARGET_MIN_HEIGHT_PX", "50"))
        filtered = []
        for item in payload.get("accepted_candidates", []):
            bbox = _bbox_xywh(item)
            if bbox is not None and bbox[2] >= min_width and bbox[3] >= min_height:
                filtered.append(item)
        payload["accepted_candidates"] = filtered
        payload["detections"] = filtered
        payload["target"] = filtered[0] if filtered else None
        payload.setdefault("quality_gate", {})["state"] = "candidate_accepted" if filtered else "no_plausible_size_candidate"
        payload["quality_gate"]["min_size_px"] = [min_width, min_height]
        _write_json_atomic(out_dir / context_name, payload)
        target = payload.get("target") if isinstance(payload.get("target"), dict) else None
        candidates = [item for item in payload.get("accepted_candidates", []) if isinstance(item, dict)]
        gate = payload.get("quality_gate") if isinstance(payload.get("quality_gate"), dict) else {}
        return target, gate, candidates
    frame = read_complete_jpeg_image(frame_path)
    if frame is None:
        return None, {
            "schema_version": "target_quality_gate_v2",
            "state": f"missing_{side}_frame",
            "detector": "pretrained_yolo_coco_target_detector",
            "control_boundary": "target_quality_gate_only_not_motion_permission",
        }, []
    resized = cv2.resize(frame, (args.target_imgsz, args.target_imgsz))
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    tensor = (rgb.astype("float32") / 255.0).transpose(2, 0, 1).reshape(1, 3, args.target_imgsz, args.target_imgsz)
    try:
        payload = _detect_target_tensor_cached(tensor, args.target_model, args.target_conf, args.target_imgsz, frame.shape[1], frame.shape[0])
    except Exception as exc:
        payload = {
            "target": None,
            "accepted_candidates": [],
            "quality_gate": {
                "schema_version": "target_quality_gate_v2",
                "state": "cached_ort_detector_error",
                "error": str(exc),
                "detector": "pretrained_yolo_coco_target_detector",
                "control_boundary": "target_quality_gate_only_not_motion_permission",
            },
        }
    _write_json_atomic(out_dir / context_name, payload)
    target = payload.get("target") if isinstance(payload.get("target"), dict) else None
    candidates = [item for item in payload.get("accepted_candidates", []) if isinstance(item, dict)]
    if target and not candidates:
        candidates = [target]
    gate = payload.get("quality_gate") if isinstance(payload.get("quality_gate"), dict) else {}
    return target, gate, candidates


def _bbox_xywh(item: dict[str, Any] | None) -> list[float] | None:
    if not isinstance(item, dict):
        return None
    bbox = item.get("bbox_xywh") or item.get("bbox")
    if not isinstance(bbox, list) or len(bbox) < 4:
        return None
    try:
        return [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])]
    except (TypeError, ValueError):
        return None


def _bbox_iou(a: list[float], b: list[float]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ax2 = ax + aw
    ay2 = ay + ah
    bx2 = bx + bw
    by2 = by + bh
    ix1 = max(ax, bx)
    iy1 = max(ay, by)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _bbox_center_inside(inner: list[float], outer: list[float]) -> bool:
    x, y, width, height = inner
    ox, oy, ow, oh = outer
    cx = x + width / 2.0
    cy = y + height / 2.0
    return ox <= cx <= ox + ow and oy <= cy <= oy + oh


def _center_from_bbox(bbox: list[float]) -> list[float]:
    return [round(float(bbox[0]) + float(bbox[2]) / 2.0, 2), round(float(bbox[1]) + float(bbox[3]) / 2.0, 2)]


def _smooth_bbox(prev: list[float], current: list[float], alpha: float) -> list[float]:
    a = max(0.0, min(1.0, float(alpha)))
    return [round(float(prev[i]) * (1.0 - a) + float(current[i]) * a, 2) for i in range(4)]


def stabilize_target_detection(
    raw_target: dict[str, Any] | None,
    side: str,
    args: argparse.Namespace,
    frame_index: int,
    ts: float,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    tracker = TARGET_TRACKERS.setdefault(side, {})
    ttl = max(0.0, float(args.visual_memory_ttl))
    max_misses = max(0, int(args.visual_memory_max_misses))
    alpha = max(0.0, min(1.0, float(args.visual_ema_alpha)))
    raw_bbox = _bbox_xywh(raw_target)
    if isinstance(raw_target, dict) and raw_bbox is not None:
        prev_bbox = _bbox_xywh(tracker.get("target"))
        smoothed_bbox = raw_bbox
        smoothed = False
        if prev_bbox is not None and _bbox_iou(prev_bbox, raw_bbox) >= 0.02:
            smoothed_bbox = _smooth_bbox(prev_bbox, raw_bbox, alpha)
            smoothed = True
        target = dict(raw_target)
        target["bbox_xywh"] = smoothed_bbox
        target["center_px"] = _center_from_bbox(smoothed_bbox)
        target["tracking_state"] = "fresh_smoothed" if smoothed else "fresh_detected"
        target["tracking_side"] = side
        target["tracking_frame_index"] = frame_index
        target["raw_bbox_xywh"] = [round(float(v), 2) for v in raw_bbox]
        tracker.update(
            {
                "target": target,
                "last_seen_ts": ts,
                "last_seen_frame": frame_index,
                "misses": 0,
                "hits": int(tracker.get("hits") or 0) + 1,
            }
        )
        return target, {
            "state": target["tracking_state"],
            "side": side,
            "hit_streak": tracker["hits"],
            "missing_frames": 0,
            "age_s": 0.0,
            "ema_alpha": alpha,
            "control_boundary": "visual_memory_tracker_only_not_motion_permission",
        }
    previous = tracker.get("target") if isinstance(tracker.get("target"), dict) else None
    if previous is not None:
        age_s = max(0.0, ts - float(tracker.get("last_seen_ts") or ts))
        misses = int(tracker.get("misses") or 0) + 1
        tracker["misses"] = misses
        if age_s <= ttl and misses <= max_misses:
            retained = dict(previous)
            retained["source"] = "visual_memory_tracker"
            retained["tracking_state"] = "memory_retained"
            retained["tracking_side"] = side
            retained["tracking_frame_index"] = frame_index
            retained["tracking_age_s"] = round(age_s, 3)
            retained["tracking_missing_frames"] = misses
            if isinstance(retained.get("confidence"), (int, float)):
                decay = max(0.45, 1.0 - (age_s / max(ttl, 0.001)) * 0.55)
                retained["confidence"] = round(float(retained["confidence"]) * decay, 4)
            return retained, {
                "state": "memory_retained",
                "side": side,
                "hit_streak": int(tracker.get("hits") or 0),
                "missing_frames": misses,
                "age_s": round(age_s, 3),
                "ttl_s": ttl,
                "max_misses": max_misses,
                "control_boundary": "visual_memory_tracker_only_not_motion_permission",
            }
    return None, {
        "state": "unlocked",
        "side": side,
        "hit_streak": int(tracker.get("hits") or 0),
        "missing_frames": int(tracker.get("misses") or 0),
        "control_boundary": "visual_memory_tracker_only_not_motion_permission",
    }

def detection_center_px(item: dict[str, Any] | None) -> tuple[float, float] | None:
    if not isinstance(item, dict):
        return None
    center = item.get("center_px") or item.get("center_xy")
    if isinstance(center, list) and len(center) >= 2:
        try:
            return float(center[0]), float(center[1])
        except (TypeError, ValueError):
            return None
    bbox = _bbox_xywh(item)
    if bbox is None:
        return None
    return bbox[0] + bbox[2] / 2.0, bbox[1] + bbox[3] / 2.0


def pixel_to_camera_frame(
    calibration: dict[str, Any] | None,
    pixel: tuple[float, float] | list[float] | None,
    depth_m: float | None,
) -> dict[str, float] | None:
    if not calibration or not pixel or depth_m is None:
        return None
    try:
        z = float(depth_m)
        if not np.isfinite(z) or z <= 0:
            return None
        rectification = calibration.get("rectification") if isinstance(calibration.get("rectification"), dict) else {}
        p1 = np.asarray(rectification.get("P1") or calibration.get("left_intrinsics"), dtype=np.float64)
        fx = float(p1[0, 0])
        fy = float(p1[1, 1])
        cx = float(p1[0, 2])
        cy = float(p1[1, 2])
        u = float(pixel[0])
        v = float(pixel[1])
        return {
            "x_m": round((u - cx) * z / fx, 5),
            "y_m": round((v - cy) * z / fy, 5),
            "z_m": round(z, 5),
        }
    except Exception:
        return None


def camera_frame_delta(a: dict[str, float] | None, b: dict[str, float] | None) -> dict[str, float] | None:
    if not a or not b:
        return None
    try:
        dx = float(a["x_m"]) - float(b["x_m"])
        dy = float(a["y_m"]) - float(b["y_m"])
        dz = float(a["z_m"]) - float(b["z_m"])
        return {
            "dx_m": round(dx, 5),
            "dy_m": round(dy, 5),
            "dz_m": round(dz, 5),
            "distance_m": round(float((dx * dx + dy * dy + dz * dz) ** 0.5), 5),
        }
    except Exception:
        return None


def load_stereo_calibration(path_text: str) -> dict[str, Any] | None:
    if not path_text:
        return None
    path = Path(path_text)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) and payload.get("calibration_state") == "calibrated" else None


def assess_stereo_bbox_compatibility(
    left_target: dict[str, Any],
    right_target: dict[str, Any],
) -> dict[str, Any]:
    left_bbox = _bbox_xywh(left_target)
    right_bbox = _bbox_xywh(right_target)
    if left_bbox is None or right_bbox is None:
        return {"state": "rejected", "reason": "missing_left_or_right_bbox"}

    left_width, left_height = left_bbox[2], left_bbox[3]
    right_width, right_height = right_bbox[2], right_bbox[3]
    if min(left_width, left_height, right_width, right_height) <= 0:
        return {"state": "rejected", "reason": "invalid_left_or_right_bbox"}

    width_ratio = min(left_width, right_width) / max(left_width, right_width)
    height_ratio = min(left_height, right_height) / max(left_height, right_height)
    area_ratio = min(left_width * left_height, right_width * right_height) / max(
        left_width * left_height,
        right_width * right_height,
    )
    left_aspect = left_width / left_height
    right_aspect = right_width / right_height
    aspect_ratio = min(left_aspect, right_aspect) / max(left_aspect, right_aspect)
    gates = {
        "min_width_ratio": float(os.environ.get("REHAB_STEREO_MIN_BBOX_WIDTH_RATIO", "0.60")),
        "min_height_ratio": float(os.environ.get("REHAB_STEREO_MIN_BBOX_HEIGHT_RATIO", "0.60")),
        "min_area_ratio": float(os.environ.get("REHAB_STEREO_MIN_BBOX_AREA_RATIO", "0.50")),
        "min_aspect_ratio": float(os.environ.get("REHAB_STEREO_MIN_BBOX_ASPECT_RATIO", "0.65")),
    }
    metrics = {
        "width_ratio": round(width_ratio, 4),
        "height_ratio": round(height_ratio, 4),
        "area_ratio": round(area_ratio, 4),
        "aspect_ratio": round(aspect_ratio, 4),
    }
    accepted = (
        width_ratio >= gates["min_width_ratio"]
        and height_ratio >= gates["min_height_ratio"]
        and area_ratio >= gates["min_area_ratio"]
        and aspect_ratio >= gates["min_aspect_ratio"]
    )
    return {
        "state": "accepted" if accepted else "rejected",
        "reason": "compatible_stereo_bbox_geometry" if accepted else "bbox_geometry_mismatch",
        "metrics": metrics,
        "gates": gates,
        "control_boundary": "stereo_bbox_pair_gate_only_not_motion_permission",
    }


def summarize_dense_disparities(
    disparities: np.ndarray,
    *,
    focal_px: float,
    baseline_m: float,
    min_valid_pixels: int = 256,
) -> dict[str, Any]:
    values = np.asarray(disparities, dtype=np.float64).reshape(-1)
    values = values[np.isfinite(values) & (values > 1.0)]
    if values.size < min_valid_pixels:
        return {
            "state": "rejected",
            "reason": "too_few_valid_disparity_pixels",
            "valid_disparity_pixels": int(values.size),
            "minimum_valid_pixels": int(min_valid_pixels),
        }
    median_disparity = float(np.median(values))
    q25, q75 = np.percentile(values, [25, 75])
    depth_m = float(focal_px * baseline_m / median_disparity)
    if not np.isfinite(depth_m) or not 0.15 <= depth_m <= 3.0:
        return {
            "state": "rejected",
            "reason": "dense_depth_out_of_range",
            "valid_disparity_pixels": int(values.size),
            "median_disparity_px": round(median_disparity, 4),
            "depth_m": round(depth_m, 5) if np.isfinite(depth_m) else None,
        }
    return {
        "state": "accepted",
        "reason": "robust_dense_roi_median",
        "valid_disparity_pixels": int(values.size),
        "median_disparity_px": round(median_disparity, 4),
        "disparity_iqr_px": round(float(q75 - q25), 4),
        "depth_m": round(depth_m, 5),
    }


def choose_dense_reference_candidate(
    candidates: list[dict[str, Any]],
    frame_width: int = 640,
    frame_height: int = 480,
) -> dict[str, Any] | None:
    margin = float(os.environ.get("REHAB_STEREO_DENSE_EDGE_MARGIN_PX", "4"))
    complete: list[dict[str, Any]] = []
    for candidate in candidates:
        bbox = _bbox_xywh(candidate)
        if bbox is None:
            continue
        x, y, width, height = bbox
        if x <= margin or y <= margin or x + width >= frame_width - margin or y + height >= frame_height - margin:
            continue
        complete.append(candidate)
    if not complete:
        return None
    return max(complete, key=lambda item: float(item.get("confidence") or 0.0))


def assess_dense_temporal_consistency(
    depth_m: float,
    recent_point_depths: list[float],
    *,
    max_relative_delta: float,
) -> dict[str, Any]:
    if len(recent_point_depths) < 3:
        return {"state": "accepted", "reason": "insufficient_history_for_cross_method_gate"}
    reference_depth_m = float(np.median(np.asarray(recent_point_depths, dtype=np.float64)))
    relative_delta = abs(float(depth_m) - reference_depth_m) / max(reference_depth_m, 1e-6)
    return {
        "state": "accepted" if relative_delta <= max_relative_delta else "rejected",
        "reason": "dense_depth_consistent_with_recent_point_stereo"
        if relative_delta <= max_relative_delta
        else "dense_depth_temporal_inconsistent",
        "reference_depth_m": round(reference_depth_m, 5),
        "relative_delta": round(relative_delta, 5),
        "max_relative_delta": max_relative_delta,
        "reference_samples": len(recent_point_depths),
    }


def dense_stereo_depth_from_single_target(
    calibration: dict[str, Any] | None,
    left_image_path: Path,
    right_image_path: Path,
    left_target: dict[str, Any] | None,
    right_target: dict[str, Any] | None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    if not calibration:
        return {"state": "rejected", "reason": "dense_fallback_missing_calibration"}
    rectification = calibration.get("rectification") if isinstance(calibration.get("rectification"), dict) else {}
    try:
        left_mtx = np.asarray(calibration["left_intrinsics"], dtype=np.float64)
        right_mtx = np.asarray(calibration["right_intrinsics"], dtype=np.float64)
        left_dist = np.asarray(calibration["left_distortion"], dtype=np.float64).reshape(-1, 1)
        right_dist = np.asarray(calibration["right_distortion"], dtype=np.float64).reshape(-1, 1)
        r1 = np.asarray(rectification["R1"], dtype=np.float64)
        r2 = np.asarray(rectification["R2"], dtype=np.float64)
        p1 = np.asarray(rectification["P1"], dtype=np.float64)
        p2 = np.asarray(rectification["P2"], dtype=np.float64)
        left_image = read_complete_jpeg_image(left_image_path)
        right_image = read_complete_jpeg_image(right_image_path)
        if left_image is None or right_image is None or left_image.shape != right_image.shape:
            raise ValueError("stereo images missing or shape mismatch")
    except Exception as exc:
        return {"state": "rejected", "reason": f"dense_fallback_input_error:{exc}"}

    height, width = left_image.shape[:2]
    size = (width, height)
    expected_negative_disparity = float(p2[0, 3]) > 0
    reference_target = right_target if expected_negative_disparity else left_target
    reference_side = "right" if expected_negative_disparity else "left"
    reference_bbox = _bbox_xywh(reference_target)
    if reference_bbox is None:
        return {
            "state": "rejected",
            "reason": "dense_fallback_missing_reference_side_target",
            "required_reference_side": reference_side,
        }

    cache_key = (str(calibration.get("calibration_id") or "unknown"), width, height)
    cached_maps = STEREO_RECTIFY_MAP_CACHE.get(cache_key)
    if cached_maps is None:
        left_maps = cv2.initUndistortRectifyMap(left_mtx, left_dist, r1, p1, size, cv2.CV_32FC1)
        right_maps = cv2.initUndistortRectifyMap(right_mtx, right_dist, r2, p2, size, cv2.CV_32FC1)
        STEREO_RECTIFY_MAP_CACHE.clear()
        STEREO_RECTIFY_MAP_CACHE[cache_key] = (left_maps, right_maps)
    else:
        left_maps, right_maps = cached_maps
    left_rectified = cv2.remap(left_image, left_maps[0], left_maps[1], cv2.INTER_LINEAR)
    right_rectified = cv2.remap(right_image, right_maps[0], right_maps[1], cv2.INTER_LINEAR)
    if expected_negative_disparity:
        matcher_left, matcher_right = right_rectified, left_rectified
        reference_mtx, reference_dist, reference_r, reference_p = right_mtx, right_dist, r2, p2
    else:
        matcher_left, matcher_right = left_rectified, right_rectified
        reference_mtx, reference_dist, reference_r, reference_p = left_mtx, left_dist, r1, p1

    dense_scale = min(1.0, max(0.25, float(os.environ.get("REHAB_STEREO_DENSE_SCALE", "0.5"))))
    if dense_scale < 0.999:
        matcher_left = cv2.resize(matcher_left, None, fx=dense_scale, fy=dense_scale, interpolation=cv2.INTER_AREA)
        matcher_right = cv2.resize(matcher_right, None, fx=dense_scale, fy=dense_scale, interpolation=cv2.INTER_AREA)
    left_gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(cv2.cvtColor(matcher_left, cv2.COLOR_BGR2GRAY))
    right_gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(cv2.cvtColor(matcher_right, cv2.COLOR_BGR2GRAY))
    full_disparities = max(16, int(os.environ.get("REHAB_STEREO_DENSE_FULL_DISPARITIES", "128")))
    num_disparities = max(16, int(np.ceil(full_disparities * dense_scale / 16.0)) * 16)
    matcher = cv2.StereoSGBM_create(
        minDisparity=0,
        numDisparities=num_disparities,
        blockSize=3,
        P1=8 * 3 * 3,
        P2=32 * 3 * 3,
        disp12MaxDiff=5,
        uniquenessRatio=0,
        speckleWindowSize=0,
        preFilterCap=63,
        mode=cv2.STEREO_SGBM_MODE_SGBM,
    )
    disparity = matcher.compute(left_gray, right_gray).astype(np.float32) / 16.0

    x, y, box_width, box_height = reference_bbox
    corners = np.asarray(
        [[[x, y]], [[x + box_width, y]], [[x, y + box_height]], [[x + box_width, y + box_height]]],
        dtype=np.float64,
    )
    rectified_corners = cv2.undistortPoints(
        corners, reference_mtx, reference_dist, R=reference_r, P=reference_p
    ).reshape(-1, 2)
    low = np.floor(rectified_corners.min(axis=0)).astype(int)
    high = np.ceil(rectified_corners.max(axis=0)).astype(int)
    roi_width = max(1, int(high[0] - low[0]))
    roi_height = max(1, int(high[1] - low[1]))
    inset_x = int(roi_width * 0.18)
    inset_y = int(roi_height * 0.18)
    x1_full = max(0, int(low[0]) + inset_x)
    y1_full = max(0, int(low[1]) + inset_y)
    x2_full = min(width, int(high[0]) - inset_x)
    y2_full = min(height, int(high[1]) - inset_y)
    x1 = int(x1_full * dense_scale)
    y1 = int(y1_full * dense_scale)
    x2 = int(x2_full * dense_scale)
    y2 = int(y2_full * dense_scale)
    if x2 <= x1 or y2 <= y1:
        return {"state": "rejected", "reason": "dense_fallback_empty_rectified_roi"}

    summary = summarize_dense_disparities(
        disparity[y1:y2, x1:x2],
        focal_px=float(p1[0, 0]) * dense_scale,
        baseline_m=float(calibration.get("baseline_m") or abs(float(p2[0, 3]) / float(p1[0, 0]))),
        min_valid_pixels=int(os.environ.get("REHAB_STEREO_DENSE_MIN_PIXELS", "256")),
    )
    if summary["state"] != "accepted":
        return {**summary, "method": "rectified_sgbm_single_eye_roi", "reference_side": reference_side}

    center = rectified_corners.mean(axis=0)
    depth_m = float(summary["depth_m"])
    fx, fy = float(p1[0, 0]), float(p1[1, 1])
    cx, cy = float(p1[0, 2]), float(p1[1, 2])
    return {
        **summary,
        "reason": "dense_rectified_roi_single_eye_fallback",
        "method": "rectified_sgbm_single_eye_roi",
        "reference_side": reference_side,
        "rectified_roi_xyxy": [x1_full, y1_full, x2_full, y2_full],
        "dense_scale": dense_scale,
        "dense_num_disparities": num_disparities,
        "dense_compute_ms": round((time.perf_counter() - started_at) * 1000.0, 3),
        "calibration_id": calibration.get("calibration_id"),
        "calibration_kind": calibration.get("calibration_kind", "chessboard_stereo"),
        "calibration_transform_state": calibration.get("transform_state"),
        "calibration_warning": calibration.get("warning"),
        "target_3d_camera_frame": {
            "x_m": round((float(center[0]) - cx) * depth_m / fx, 5),
            "y_m": round((float(center[1]) - cy) * depth_m / fy, 5),
            "z_m": round(depth_m, 5),
        },
        "warning": "Single-eye YOLO ROI with dense stereo median; provisional evidence, not motion permission.",
        "control_boundary": "dense_stereo_depth_evidence_only_not_motion_permission",
    }


def stereo_depth_from_targets(calibration: dict[str, Any] | None, left_target: dict[str, Any] | None, right_target: dict[str, Any] | None) -> dict[str, Any]:
    if not calibration:
        return {"state": "waiting_calibration", "reason": "stereo_calibration_json_missing_or_not_calibrated"}
    if not left_target or not right_target or left_target.get("label") != right_target.get("label"):
        return {"state": "waiting_stereo_match", "reason": "no_same_label_left_right_detection"}
    left_center = detection_center_px(left_target)
    right_center = detection_center_px(right_target)
    if not left_center or not right_center:
        return {"state": "waiting_stereo_match", "reason": "missing_left_or_right_center"}
    bbox_compatibility = assess_stereo_bbox_compatibility(left_target, right_target)
    if bbox_compatibility["state"] != "accepted":
        return {
            "state": "rejected",
            "reason": bbox_compatibility["reason"],
            "bbox_compatibility": bbox_compatibility,
        }
    rectification = calibration.get("rectification") if isinstance(calibration.get("rectification"), dict) else {}
    required = ["left_intrinsics", "right_intrinsics", "left_distortion", "right_distortion"]
    if not all(calibration.get(key) for key in required) or not all(rectification.get(key) for key in ("R1", "R2", "P1", "P2")):
        return {"state": "waiting_calibration", "reason": "calibration_missing_intrinsics_or_rectification"}
    try:
        left_mtx = np.asarray(calibration["left_intrinsics"], dtype=np.float64)
        right_mtx = np.asarray(calibration["right_intrinsics"], dtype=np.float64)
        left_dist = np.asarray(calibration["left_distortion"], dtype=np.float64).reshape(-1, 1)
        right_dist = np.asarray(calibration["right_distortion"], dtype=np.float64).reshape(-1, 1)
        r1 = np.asarray(rectification["R1"], dtype=np.float64)
        r2 = np.asarray(rectification["R2"], dtype=np.float64)
        p1 = np.asarray(rectification["P1"], dtype=np.float64)
        p2 = np.asarray(rectification["P2"], dtype=np.float64)
        left_rect = cv2.undistortPoints(np.asarray([[left_center]], dtype=np.float64), left_mtx, left_dist, R=r1, P=p1).reshape(2)
        right_rect = cv2.undistortPoints(np.asarray([[right_center]], dtype=np.float64), right_mtx, right_dist, R=r2, P=p2).reshape(2)
        disparity_px = float(left_rect[0] - right_rect[0])
        fx = float(p1[0, 0])
        fy = float(p1[1, 1])
        cx = float(p1[0, 2])
        cy = float(p1[1, 2])
        projection_tx_m = float(p2[0, 3]) / fx
        baseline_m = float(calibration.get("baseline_m") or abs(projection_tx_m))
    except Exception as exc:
        return {"state": "waiting_depth_runtime", "reason": f"calibration_projection_failed:{exc}"}
    allow_swapped = os.environ.get("REHAB_STEREO_ALLOW_SWAPPED", "0") == "1"
    max_vertical_delta_px = float(os.environ.get("REHAB_STEREO_MAX_VERTICAL_DELTA_PX", "8.0"))
    camera_order = "normal"
    order_warning = None
    expected_disparity_sign = -1.0 if projection_tx_m > 0 else 1.0
    signed_disparity_px = disparity_px * expected_disparity_sign
    if not np.isfinite(disparity_px) or signed_disparity_px <= 0.5:
        swapped_disparity_px = float(right_rect[0] - left_rect[0]) if np.isfinite(disparity_px) else float("nan")
        swapped_vertical_delta_px = float(right_rect[1] - left_rect[1]) if np.isfinite(disparity_px) else float("nan")
        swapped_signed_disparity_px = swapped_disparity_px * expected_disparity_sign
        if allow_swapped and np.isfinite(swapped_disparity_px) and swapped_signed_disparity_px > 0.5 and abs(swapped_vertical_delta_px) <= max_vertical_delta_px:
            left_rect, right_rect = right_rect, left_rect
            disparity_px = swapped_disparity_px
            vertical_delta_px = swapped_vertical_delta_px
            camera_order = "swapped_left_right_fallback"
            order_warning = "camera_order_or_calibration_side_mismatch; depth is a demo candidate until stereo mapping is revalidated"
        else:
            return {
                "state": "rejected",
                "reason": "non_positive_or_too_small_rectified_disparity",
                "disparity_px": round(disparity_px, 4) if np.isfinite(disparity_px) else None,
                "swapped_disparity_px": round(swapped_disparity_px, 4) if np.isfinite(swapped_disparity_px) else None,
                "swapped_vertical_delta_px": round(swapped_vertical_delta_px, 4) if np.isfinite(swapped_vertical_delta_px) else None,
                "swapped_fallback_available": bool(allow_swapped),
                "expected_disparity_sign": "negative" if expected_disparity_sign < 0 else "positive",
            }
    depth_m = abs(fx * baseline_m / disparity_px)
    if not np.isfinite(depth_m) or depth_m <= 0:
        return {"state": "rejected", "reason": "invalid_depth", "disparity_px": round(disparity_px, 4)}
    min_depth_m = float(os.environ.get("REHAB_STEREO_MIN_DEPTH_M", "0.15"))
    max_depth_m = float(os.environ.get("REHAB_STEREO_MAX_DEPTH_M", "2.0"))
    if not min_depth_m <= depth_m <= max_depth_m:
        return {
            "state": "rejected",
            "reason": "depth_outside_workspace_range",
            "depth_m": round(float(depth_m), 5),
            "depth_gate_m": [min_depth_m, max_depth_m],
            "disparity_px": round(disparity_px, 4),
            "calibration_id": calibration.get("calibration_id"),
            "control_boundary": "stereo_depth_evidence_only_not_motion_permission",
        }
    vertical_delta_px = float(left_rect[1] - right_rect[1])
    state = "accepted" if abs(vertical_delta_px) <= max_vertical_delta_px else "rejected"
    x_m = (float(left_rect[0]) - cx) * depth_m / fx
    y_m = (float(left_rect[1]) - cy) * depth_m / fy
    return {
        "state": state,
        "reason": ("rectified_stereo_match" if camera_order == "normal" else "swapped_left_right_order_fallback") if state == "accepted" else "rectified_vertical_mismatch",
        "calibration_id": calibration.get("calibration_id"),
        "calibration_kind": calibration.get("calibration_kind", "chessboard_stereo"),
        "calibration_transform_state": calibration.get("transform_state"),
        "calibration_warning": calibration.get("warning"),
        "disparity_px": round(disparity_px, 4),
        "camera_order": camera_order,
        "expected_disparity_sign": "negative" if expected_disparity_sign < 0 else "positive",
        "order_warning": order_warning,
        "depth_m": round(float(depth_m), 5),
        "rectified_vertical_delta_px": round(vertical_delta_px, 4),
        "vertical_delta_gate_px": max_vertical_delta_px,
        "left_center_px": [round(left_center[0], 3), round(left_center[1], 3)],
        "right_center_px": [round(right_center[0], 3), round(right_center[1], 3)],
        "bbox_compatibility": bbox_compatibility,
        "target_3d_camera_frame": {"x_m": round(float(x_m), 5), "y_m": round(float(y_m), 5), "z_m": round(float(depth_m), 5)},
        "control_boundary": "stereo_depth_evidence_only_not_motion_permission",
    }


def choose_stereo_target_pair(
    calibration: dict[str, Any] | None,
    left_candidates: list[dict[str, Any]],
    right_candidates: list[dict[str, Any]],
    default_left: dict[str, Any] | None,
    default_right: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any]]:
    left_pool = left_candidates or ([default_left] if default_left else [])
    right_pool = right_candidates or ([default_right] if default_right else [])
    best: tuple[float, dict[str, Any], dict[str, Any], dict[str, Any]] | None = None
    rejected_samples: list[dict[str, Any]] = []
    for li, left in enumerate(left_pool):
        if not isinstance(left, dict):
            continue
        for ri, right in enumerate(right_pool):
            if not isinstance(right, dict):
                continue
            evidence = stereo_depth_from_targets(calibration, left, right)
            lconf = float(left.get("confidence") or 0.0)
            rconf = float(right.get("confidence") or 0.0)
            vertical = abs(float(evidence.get("rectified_vertical_delta_px") or evidence.get("swapped_vertical_delta_px") or 9999.0))
            disparity = abs(float(evidence.get("disparity_px") or evidence.get("swapped_disparity_px") or 0.0))
            score = vertical - 12.0 * min(lconf, rconf) - 0.015 * disparity
            sample = {
                "left_index": li,
                "right_index": ri,
                "state": evidence.get("state"),
                "reason": evidence.get("reason"),
                "vertical_delta_px": evidence.get("rectified_vertical_delta_px", evidence.get("swapped_vertical_delta_px")),
                "disparity_px": evidence.get("disparity_px", evidence.get("swapped_disparity_px")),
                "left_confidence": left.get("confidence"),
                "right_confidence": right.get("confidence"),
            }
            if evidence.get("state") == "accepted":
                if best is None or score < best[0]:
                    best = (score, left, right, evidence)
            elif len(rejected_samples) < 6:
                rejected_samples.append(sample)
    if best is not None:
        _, left, right, evidence = best
        evidence["pair_selection"] = {
            "schema_version": "stereo_target_pair_selection_v1",
            "state": "accepted_geometry_pair",
            "left_candidates": len(left_pool),
            "right_candidates": len(right_pool),
            "policy": "choose accepted pair with smallest rectified vertical delta and useful confidence",
            "control_boundary": "stereo_pair_selection_only_not_motion_permission",
        }
        return left, right, evidence
    fallback = stereo_depth_from_targets(calibration, default_left, default_right)
    fallback["pair_selection"] = {
        "schema_version": "stereo_target_pair_selection_v1",
        "state": "no_geometry_pair",
        "left_candidates": len(left_pool),
        "right_candidates": len(right_pool),
        "rejected_samples": rejected_samples,
        "control_boundary": "stereo_pair_selection_only_not_motion_permission",
    }
    return default_left, default_right, fallback



def assess_effector_candidate(
    item: dict[str, Any],
    frame_width: int = 640,
    frame_height: int = 480,
    target: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    bbox = _bbox_xywh(item)
    if bbox is None:
        return False, "missing_bbox"
    x, y, width, height = bbox
    if width < 10 or height < 10:
        return False, "bbox_too_small"
    frame_area = max(1.0, float(frame_width * frame_height))
    area_ratio = float(width * height) / frame_area
    max_area_ratio = float(os.environ.get("REHAB_END_EFFECTOR_MAX_AREA_RATIO", "0.045"))
    if area_ratio > max_area_ratio:
        return False, "bbox_too_large"
    min_y_ratio = float(os.environ.get("REHAB_END_EFFECTOR_MIN_Y_RATIO", "0.16"))
    if y < frame_height * min_y_ratio:
        return False, "bbox_in_top_band"
    aspect = float(width) / max(1.0, float(height))
    if aspect < 0.22 or aspect > 4.8:
        return False, "aspect_implausible"
    confidence = item.get("confidence")
    if isinstance(confidence, (int, float)) and float(confidence) < 0.20:
        return False, "confidence_too_low"
    touched_edges = 0
    if x <= 2:
        touched_edges += 1
    if y <= 2:
        touched_edges += 1
    if x + width >= frame_width - 2:
        touched_edges += 1
    if y + height >= frame_height - 2:
        touched_edges += 1
    if touched_edges >= 2:
        return False, "bbox_touches_multiple_edges"
    target_bbox = _bbox_xywh(target)
    if target_bbox is not None:
        overlap = _bbox_iou(bbox, target_bbox)
        if _bbox_center_inside(bbox, target_bbox) and overlap >= 0.08:
            return False, "target_overlap_ambiguous"
    return True, "accepted"


def filter_effector_detections(detections: list[Any], target: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    rejected_samples: list[dict[str, Any]] = []
    rejection_reasons: dict[str, int] = {}
    rejected_count = 0
    for det in detections:
        if not isinstance(det, dict):
            continue
        label = str(det.get("label") or "")
        if label not in {"end_effector", "gripper_tip"}:
            continue
        ok, reason = assess_effector_candidate(det, target=target)
        if ok:
            accepted.append(det)
        else:
            rejected_count += 1
            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
            if len(rejected_samples) < 4:
                rejected_samples.append(
                    {
                        "label": label,
                        "confidence": det.get("confidence"),
                        "bbox_xywh": _bbox_xywh(det),
                        "reason": reason,
                    }
                )
    return accepted, {
        "schema_version": "end_effector_quality_gate_v1",
        "state": "candidate_accepted" if accepted else "no_plausible_end_effector",
        "accepted_count": len(accepted),
        "rejected_count": rejected_count,
        "rejection_reasons": rejection_reasons,
        "rejected_samples": rejected_samples,
        "max_bbox_area_ratio": float(os.environ.get("REHAB_END_EFFECTOR_MAX_AREA_RATIO", "0.045")),
        "min_y_ratio": float(os.environ.get("REHAB_END_EFFECTOR_MIN_Y_RATIO", "0.16")),
        "min_confidence": 0.20,
        "target_overlap_policy": "reject_when_effector_center_inside_target_and_iou_ge_0.08",
        "confidence_note": "raw_yolov8_confidence_scaled_to_frame_coordinates; below 0.5 remains weak evidence",
        "control_boundary": "end_effector_quality_gate_only_not_motion_permission",
    }


def maybe_save_hard_negative(args: argparse.Namespace, target: dict[str, Any] | None, gate: dict[str, Any], frame_index: int, ts: float) -> dict[str, Any] | None:
    reasons = gate.get("rejection_reasons") if isinstance(gate.get("rejection_reasons"), dict) else {}
    if int(reasons.get("target_overlap_ambiguous", 0) or 0) <= 0:
        return None
    source = Path(args.out_dir) / "latest_left.jpg"
    if not source.is_file():
        return None
    out_dir = Path(args.hard_negative_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(ts))
    stem = f"target_overlap_{stamp}_{frame_index:06d}"
    image_path = out_dir / f"{stem}.jpg"
    meta_path = out_dir / f"{stem}.json"
    shutil.copy2(source, image_path)
    metadata = {
        "schema_version": "rehab_vla_hard_negative_v1",
        "reason": "target_overlap_ambiguous",
        "frame_index": frame_index,
        "frame_ts_unix": ts,
        "source_image": str(image_path),
        "target_object": target,
        "rejected_samples": gate.get("rejected_samples") if isinstance(gate.get("rejected_samples"), list) else [],
        "labeling_hint": "Treat rejected end-effector/gripper-tip candidates as negatives unless the real arm endpoint is visibly separate from the target.",
        "control_boundary": "dataset_capture_only_not_motion_permission",
    }
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "schema_version": "hard_negative_capture_v1",
        "state": "saved",
        "reason": "target_overlap_ambiguous",
        "image_path": str(image_path),
        "metadata_path": str(meta_path),
        "control_boundary": "dataset_capture_only_not_motion_permission",
    }


def _draw_label_box(frame: Any, item: dict[str, Any], color: tuple[int, int, int]) -> None:
    bbox = _bbox_xywh(item)
    if bbox is None:
        return
    x, y, width, height = bbox
    x1 = max(0, min(frame.shape[1] - 1, int(round(x))))
    y1 = max(0, min(frame.shape[0] - 1, int(round(y))))
    x2 = max(0, min(frame.shape[1] - 1, int(round(x + width))))
    y2 = max(0, min(frame.shape[0] - 1, int(round(y + height))))
    if x2 <= x1 or y2 <= y1:
        return
    label = str(item.get("label") or "object")
    confidence = item.get("confidence")
    if isinstance(confidence, (int, float)):
        label = f"{label} {confidence:.2f}"
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    text_y = max(18, y1 - 7)
    cv2.putText(frame, label, (x1, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.52, color, 2)


def annotate_left_frame(args: argparse.Namespace, target: dict[str, Any] | None, detections: list[dict[str, Any]]) -> None:
    left_path = Path(args.out_dir) / "latest_left.jpg"
    frame = read_complete_jpeg_image(left_path)
    if frame is None:
        return
    if target:
        _draw_label_box(frame, target, (0, 220, 255))
    for det in detections:
        if isinstance(det, dict):
            _draw_label_box(frame, det, (255, 190, 40))
    cv2.imwrite(str(left_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 76])


def _label_of(item: dict[str, Any] | None) -> str:
    return str(item.get("label") or "") if isinstance(item, dict) else ""


def _same_label_count(samples: list[dict[str, Any]], key: str, label: str) -> int:
    if not label:
        return 0
    return sum(1 for sample in samples if sample.get(key) == label)


def _stable_pixel_delta(samples: list[dict[str, Any]], max_jitter_px: float = 18.0) -> bool:
    deltas = [sample.get("pixel_delta_px") for sample in samples if isinstance(sample.get("pixel_delta_px"), list)]
    if len(deltas) < 3:
        return False
    xs = [float(delta[0]) for delta in deltas[-3:]]
    ys = [float(delta[1]) for delta in deltas[-3:]]
    return (max(xs) - min(xs)) <= max_jitter_px and (max(ys) - min(ys)) <= max_jitter_px


def build_visual_lock_stability(
    history: list[dict[str, Any]] | deque[dict[str, Any]],
    target: dict[str, Any] | None,
    stable_effector: dict[str, Any] | None,
    pixel_delta: list[float] | None,
) -> dict[str, Any]:
    target_label = _label_of(target)
    effector_label = _label_of(stable_effector)
    has_pair = bool(target_label and effector_label and pixel_delta is not None)
    sample = {
        "target_label": target_label,
        "end_effector_label": effector_label,
        "has_pair": has_pair,
        "pixel_delta_px": pixel_delta if pixel_delta is not None else None,
    }
    history.append(sample)
    samples = list(history)
    recent = samples[-3:]
    locked_frames = sum(1 for item in recent if item.get("has_pair"))
    target_same = _same_label_count(recent, "target_label", target_label)
    effector_same = _same_label_count(recent, "end_effector_label", effector_label)
    stable = locked_frames >= 3 and target_same >= 3 and effector_same >= 3 and _stable_pixel_delta(samples)
    if stable:
        state = "stable_visual_lock"
    elif has_pair:
        state = "accumulating_visual_lock"
    else:
        state = "waiting_target_or_end_effector"
    return {
        "schema_version": "visual_lock_stability_v1",
        "state": state,
        "target_same_label_frames": target_same,
        "end_effector_same_label_frames": effector_same,
        "locked_frames": locked_frames,
        "samples": min(len(samples), 5),
        "stable": stable,
        "pixel_delta_jitter_gate_px": 18.0,
        "control_boundary": "visual_lock_only_not_motion_permission",
    }


def build_stereo_context(args: argparse.Namespace, probe_context: dict[str, Any], frame_index: int, ts: float) -> dict[str, Any]:
    detection_started = time.time()
    left_target_future = DETECTION_EXECUTOR.submit(detect_target_yolo, args, "left")
    global LATEST_ORT_PAYLOAD, LATEST_ORT_FRAME_INDEX, LATEST_RIGHT_TARGET_RESULT, LATEST_RIGHT_TARGET_FRAME_INDEX
    right_target_every = max(1, int(os.environ.get("REHAB_RIGHT_TARGET_HEAVY_EVERY", "3")))
    should_refresh_right = LATEST_RIGHT_TARGET_RESULT is None or frame_index == 1 or frame_index % right_target_every == 0
    right_target_future = DETECTION_EXECUTOR.submit(detect_target_yolo, args, "right") if should_refresh_right else None
    effector_every = max(1, int(os.environ.get("REHAB_END_EFFECTOR_HEAVY_EVERY", "3")))
    should_refresh_effector = LATEST_ORT_PAYLOAD is None or frame_index == 1 or frame_index % effector_every == 0
    effector_future = DETECTION_EXECUTOR.submit(run_ort_infer, args) if should_refresh_effector else None

    raw_target, target_quality_gate, left_target_candidates = left_target_future.result()
    if should_refresh_right:
        raw_right_target, right_target_quality_gate, right_target_candidates = right_target_future.result()
        LATEST_RIGHT_TARGET_RESULT = (raw_right_target, right_target_quality_gate, right_target_candidates)
        LATEST_RIGHT_TARGET_FRAME_INDEX = frame_index
    else:
        raw_right_target, right_target_quality_gate, right_target_candidates = LATEST_RIGHT_TARGET_RESULT
        right_target_quality_gate = {
            **right_target_quality_gate,
            "state_detail": "reused_right_eye_detection_for_display_only",
            "reused_from_frame_index": LATEST_RIGHT_TARGET_FRAME_INDEX,
            "refresh_every_n_heavy_frames": right_target_every,
            "metric_depth_eligible": False,
            "control_boundary": "right_target_visual_memory_only_not_motion_permission",
        }
    target, left_target_tracking = stabilize_target_detection(raw_target, "left", args, frame_index, ts)
    right_target, right_target_tracking = stabilize_target_detection(raw_right_target, "right", args, frame_index, ts)
    if raw_target is None and target is not None:
        target_quality_gate = {
            **target_quality_gate,
            "state": "memory_retained",
            "detector": "visual_memory_tracker",
            "control_boundary": "target_quality_gate_only_not_motion_permission",
        }
    if raw_right_target is None and right_target is not None:
        right_target_quality_gate = {
            **right_target_quality_gate,
            "state": "memory_retained",
            "detector": "visual_memory_tracker",
            "control_boundary": "target_quality_gate_only_not_motion_permission",
        }
    if should_refresh_effector:
        ort_payload = effector_future.result()
        LATEST_ORT_PAYLOAD = ort_payload
        LATEST_ORT_FRAME_INDEX = frame_index
    else:
        ort_payload = dict(LATEST_ORT_PAYLOAD or {})
        ort_payload.setdefault("quality_gate", {})
        if isinstance(ort_payload.get("quality_gate"), dict):
            ort_payload["quality_gate"] = {
                **ort_payload["quality_gate"],
                "state_detail": "reused_last_end_effector_detection_for_low_latency_target_refresh",
                "reused_from_frame_index": LATEST_ORT_FRAME_INDEX,
                "refresh_every_n_heavy_frames": effector_every,
                "control_boundary": "end_effector_visual_memory_only_not_motion_permission",
            }
    raw_detections = ort_payload.get("detections") if isinstance(ort_payload.get("detections"), list) else []
    detections, effector_quality_gate = filter_effector_detections(raw_detections, target)
    hard_negative_capture = maybe_save_hard_negative(args, target, effector_quality_gate, frame_index, ts)
    end_effector = None
    gripper_tip = None
    for det in detections:
        if not isinstance(det, dict):
            continue
        if det.get("label") == "end_effector" and end_effector is None:
            end_effector = det
        if det.get("label") == "gripper_tip" and gripper_tip is None:
            gripper_tip = det
    servo_origin = gripper_tip or end_effector
    annotate_left_frame(args, target, [det for det in detections if isinstance(det, dict)])
    if servo_origin:
        EFF_HISTORY.append(servo_origin)
    stable_effector = servo_origin
    if servo_origin and len(EFF_HISTORY) >= 3:
        counts: dict[str, int] = {}
        best: dict[str, Any] | None = None
        best_count = 0
        for item in EFF_HISTORY:
            key = item.get("label", "unknown")
            counts[key] = counts.get(key, 0) + 1
            if counts[key] >= best_count:
                best = item
                best_count = counts[key]
        if best is not None and best_count >= 3:
            stable_effector = best
    scene = "yolo target visual evidence" if target else "yolo waiting target visual evidence"
    pixel_delta = None
    if target and stable_effector:
        target_center = target.get("center_px") if isinstance(target.get("center_px"), list) else None
        effector_box = stable_effector.get("bbox_xywh") if isinstance(stable_effector.get("bbox_xywh"), list) else None
        if target_center and effector_box and len(target_center) == 2 and len(effector_box) == 4:
            ex = float(effector_box[0]) + float(effector_box[2]) / 2.0
            ey = float(effector_box[1]) + float(effector_box[3]) / 2.0
            pixel_delta = [round(float(target_center[0]) - ex, 2), round(float(target_center[1]) - ey, 2)]
    visual_lock = build_visual_lock_stability(VISUAL_LOCK_HISTORY, target, stable_effector, pixel_delta)
    stereo_calibration = load_stereo_calibration(args.stereo_calibration_json)
    if raw_target is not None and raw_right_target is not None and should_refresh_right:
        selected_raw_target, selected_raw_right_target, stereo_depth_evidence = choose_stereo_target_pair(
            stereo_calibration,
            left_target_candidates,
            right_target_candidates,
            raw_target,
            raw_right_target,
        )
        if selected_raw_target is not raw_target:
            target, left_target_tracking = stabilize_target_detection(selected_raw_target, "left", args, frame_index, ts)
            raw_target = selected_raw_target
        if selected_raw_right_target is not raw_right_target:
            right_target, right_target_tracking = stabilize_target_detection(selected_raw_right_target, "right", args, frame_index, ts)
            raw_right_target = selected_raw_right_target
    else:
        stereo_depth_evidence = {
            "state": "waiting_fresh_stereo_pair",
            "reason": "right_eye_runs_at_lower_frequency_and_cached_results_are_not_used_for_metric_depth",
        }
    if (
        stereo_depth_evidence.get("state") == "accepted"
        and stereo_depth_evidence.get("reason") == "rectified_stereo_match"
        and isinstance(stereo_depth_evidence.get("depth_m"), (int, float))
    ):
        POINT_STEREO_DEPTH_HISTORY.append(float(stereo_depth_evidence["depth_m"]))
    dense_fallback_every = max(1, int(os.environ.get("REHAB_STEREO_DENSE_FALLBACK_EVERY", "4")))
    if (
        stereo_depth_evidence.get("state") != "accepted"
        and should_refresh_right
        and frame_index % dense_fallback_every == 0
    ):
        dense_evidence = dense_stereo_depth_from_single_target(
            stereo_calibration,
            Path(args.out_dir) / "latest_left.jpg",
            Path(args.out_dir) / "latest_right.jpg",
            choose_dense_reference_candidate(left_target_candidates or ([raw_target] if raw_target else [])),
            choose_dense_reference_candidate(right_target_candidates or ([raw_right_target] if raw_right_target else [])),
        )
        if dense_evidence.get("state") == "accepted":
            consistency = assess_dense_temporal_consistency(
                float(dense_evidence["depth_m"]),
                list(POINT_STEREO_DEPTH_HISTORY),
                max_relative_delta=float(os.environ.get("REHAB_STEREO_DENSE_MAX_RELATIVE_DELTA", "0.18")),
            )
            dense_evidence["temporal_consistency"] = consistency
            if consistency["state"] == "accepted":
                stereo_depth_evidence = dense_evidence
            else:
                dense_evidence["state"] = "rejected"
                dense_evidence["reason"] = consistency["reason"]
                stereo_depth_evidence["dense_fallback"] = dense_evidence
        else:
            stereo_depth_evidence["dense_fallback"] = dense_evidence
            stereo_depth_evidence["dense_fallback_every_n_frames"] = dense_fallback_every
    metric_depth_available = stereo_depth_evidence.get("state") == "accepted"
    target_3d_camera_frame = stereo_depth_evidence.get("target_3d_camera_frame") if metric_depth_available else None
    target_depth_m = stereo_depth_evidence.get("depth_m") if metric_depth_available else None
    effector_center = detection_center_px(stable_effector)
    end_effector_3d_camera_frame = pixel_to_camera_frame(stereo_calibration, effector_center, target_depth_m)
    camera_frame_delta_to_target = camera_frame_delta(target_3d_camera_frame, end_effector_3d_camera_frame)
    end_effector_depth_evidence = {
        "schema_version": "end_effector_camera_frame_v1",
        "state": "same_depth_candidate" if end_effector_3d_camera_frame else "waiting_end_effector_or_target_depth",
        "method": "left_pixel_ray_with_target_depth_assumption",
        "depth_source": "target_stereo_depth_m",
        "depth_m": target_depth_m if end_effector_3d_camera_frame else None,
        "center_px": [round(effector_center[0], 3), round(effector_center[1], 3)] if effector_center else None,
        "warning": "This is a demo candidate until the gripper has its own left-right stereo match.",
        "control_boundary": "end_effector_camera_frame_only_not_motion_permission",
    }
    detection_completed = time.time()
    return {
        "schema_version": "stereo_rgb_yolo_context_v1",
        "robot_id": args.robot_id,
        "device_id": args.device_id,
        "project_id": args.project_id,
        "frame_ts_unix": ts,
        "capture_loop": {
            "schema_version": "vla_vision_capture_loop_v1",
            "frame_index": frame_index,
            "process_ms": probe_context.get("process_ms"),
            "mode": "cpp_dual_camera_probe",
            "detector_pipeline": {
                "mode": "parallel_left_right_target_and_end_effector",
                "source_frame_index": frame_index,
                "source_frame_ts_unix": ts,
                "completed_ts_unix": detection_completed,
                "pipeline_ms": round((detection_completed - detection_started) * 1000.0, 2),
                "result_age_s_at_completion": round(max(0.0, detection_completed - ts), 3),
                "right_target_refreshed": should_refresh_right,
                "right_target_source_frame_index": frame_index if should_refresh_right else LATEST_RIGHT_TARGET_FRAME_INDEX,
                "right_target_refresh_every_n_heavy_frames": right_target_every,
                "end_effector_refreshed": should_refresh_effector,
                "end_effector_source_frame_index": frame_index if should_refresh_effector else LATEST_ORT_FRAME_INDEX,
                "control_boundary": "parallel_detection_evidence_only_not_motion_permission",
            },
            "image_orientation": {
                "left_flip": args.left_flip,
                "right_flip": args.right_flip,
                "applied_before_detection": True,
            },
            "camera_mapping": {
                "schema_version": "stereo_camera_mapping_v1",
                "mapping_state": "confirmed_from_nanopi_process_cmdline_and_visual_parallax",
                "logical_left": {
                    "camera_id": "stereo_left",
                    "device_path": args.left,
                    "flip": args.left_flip,
                    "flip_applied_before_detection": True,
                },
                "logical_right": {
                    "camera_id": "stereo_right",
                    "device_path": args.right,
                    "flip": args.right_flip,
                    "flip_applied_before_detection": True,
                },
                "control_boundary": "camera_mapping_evidence_only_not_motion_permission",
            },
            "control_boundary": "capture_loop_only_not_motion_permission",
        },
        "left_camera_id": "stereo_left",
        "right_camera_id": "stereo_right",
        "stereo_calibration_id": stereo_calibration.get("calibration_id") if stereo_calibration else "",
        "baseline_m": stereo_calibration.get("baseline_m") if stereo_calibration else 0.06,
        "image_pair_ref": {
            "left_image_url": f"/api/rehab-arm/v1/devices/{args.device_id}/camera/keyframes/stereo_left/latest/file",
            "right_image_url": f"/api/rehab-arm/v1/devices/{args.device_id}/camera/keyframes/stereo_right/latest/file",
        },
        "detections": {"left": ([target] if target else []) + detections, "right": ([right_target] if right_target else [])},
        "target_object": target,
        "raw_target_object": raw_target,
        "raw_right_target_object": raw_right_target,
        "target_candidates": {
            "left": left_target_candidates[:8],
            "right": right_target_candidates[:8],
            "control_boundary": "target_candidates_only_not_motion_permission",
        },
        "end_effector_object": stable_effector,
        "pixel_servo_hint": {
            "schema_version": "pixel_servo_hint_v1",
            "state": "waiting_target_or_end_effector" if not (target and stable_effector) else "visual_servo_adjust",
            "next_step": "hold_observe" if not (target and stable_effector) else ("dry_run_move_right" if pixel_delta and pixel_delta[0] > 0 else "dry_run_move_left"),
            "dx_px": pixel_delta[0] if pixel_delta else None,
            "dy_px": pixel_delta[1] if pixel_delta else None,
            "distance_px": round((pixel_delta[0] ** 2 + pixel_delta[1] ** 2) ** 0.5, 2) if pixel_delta else None,
            "control_boundary": "pixel_servo_hint_only_not_motion_permission",
        },
        "target_quality_gate": target_quality_gate,
        "right_target_quality_gate": right_target_quality_gate,
        "visual_memory_tracker": {
            "schema_version": "visual_memory_tracker_v1",
            "left": left_target_tracking,
            "right": right_target_tracking,
            "policy": "fresh detections update an EMA bbox; short detector dropouts retain the last target for display continuity only",
            "ttl_s": max(0.0, float(args.visual_memory_ttl)),
            "max_misses": max(0, int(args.visual_memory_max_misses)),
            "ema_alpha": max(0.0, min(1.0, float(args.visual_ema_alpha))),
            "metric_depth_requires_fresh_left_and_right": True,
            "control_boundary": "visual_memory_tracker_only_not_motion_permission",
        },
        "stereo_depth_evidence": stereo_depth_evidence,
        "estimated_depth_m": target_depth_m,
        "target_3d_camera_frame": target_3d_camera_frame,
        "end_effector_3d_camera_frame": end_effector_3d_camera_frame,
        "end_effector_depth_evidence": end_effector_depth_evidence,
        "camera_frame_delta_to_target": camera_frame_delta_to_target,
        "camera_to_robot_transform": None,
        "transform_state": "waiting",
        "target_3d_robot_frame": None,
        "end_effector_quality_gate": effector_quality_gate,
        "hard_negative_capture": hard_negative_capture,
        "visual_lock_stability": visual_lock,
        "scene_summary": scene,
        "vla_context": "C++ V observes target and end effector only; A remains dry-run until safety gates pass.",
        "confidence": max(
            [float(target.get("confidence", 0.0)) if target else 0.0]
            + [float(stable_effector.get("confidence", 0.0)) if stable_effector else 0.0]
        ),
        "control_boundary": CONTROL_BOUNDARY,
    }


def _seed_fast_tracker(state: dict[str, Any], gray: Any, detection: dict[str, Any], source_frame: int) -> bool:
    bbox = _bbox_xywh(detection)
    if bbox is None:
        return False
    x, y, width, height = bbox
    x1 = max(0, min(gray.shape[1] - 1, int(round(x))))
    y1 = max(0, min(gray.shape[0] - 1, int(round(y))))
    x2 = max(x1 + 1, min(gray.shape[1], int(round(x + width))))
    y2 = max(y1 + 1, min(gray.shape[0], int(round(y + height))))
    mask = np.zeros_like(gray)
    mask[y1:y2, x1:x2] = 255
    points = cv2.goodFeaturesToTrack(gray, mask=mask, maxCorners=50, qualityLevel=0.01, minDistance=5, blockSize=5)
    if points is None or len(points) < 4:
        state.clear()
        return False
    state.update(
        {
            "gray": gray,
            "points": points,
            "bbox": [float(x1), float(y1), float(x2 - x1), float(y2 - y1)],
            "detection": dict(detection),
            "seed_source_frame": source_frame,
            "tracked_frames": 0,
            "last_ts": time.time(),
        }
    )
    return True


def _advance_fast_tracker(state: dict[str, Any], gray: Any) -> dict[str, Any] | None:
    previous_gray = state.get("gray")
    previous_points = state.get("points")
    bbox = state.get("bbox")
    if previous_gray is None or previous_points is None or not isinstance(bbox, list):
        return None
    max_frames = max(1, int(os.environ.get("REHAB_FAST_TRACK_MAX_FRAMES", "10")))
    if int(state.get("tracked_frames") or 0) >= max_frames:
        state.clear()
        return None
    next_points, status, _ = cv2.calcOpticalFlowPyrLK(
        previous_gray,
        gray,
        previous_points,
        None,
        winSize=(21, 21),
        maxLevel=3,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03),
    )
    if next_points is None or status is None:
        state.clear()
        return None
    good_old = previous_points[status.reshape(-1) == 1].reshape(-1, 2)
    good_new = next_points[status.reshape(-1) == 1].reshape(-1, 2)
    if len(good_new) < 4:
        state.clear()
        return None
    shifts = good_new - good_old
    dx, dy = np.median(shifts, axis=0)
    residual = np.linalg.norm(shifts - np.array([dx, dy]), axis=1)
    inliers = residual <= 4.0
    if int(np.count_nonzero(inliers)) < 4 or float(np.hypot(dx, dy)) > 45.0:
        state.clear()
        return None
    x = max(0.0, min(float(gray.shape[1]) - float(bbox[2]), float(bbox[0]) + float(dx)))
    y = max(0.0, min(float(gray.shape[0]) - float(bbox[3]), float(bbox[1]) + float(dy)))
    state["gray"] = gray
    state["points"] = good_new[inliers].reshape(-1, 1, 2)
    state["bbox"] = [x, y, float(bbox[2]), float(bbox[3])]
    state["tracked_frames"] = int(state.get("tracked_frames") or 0) + 1
    state["last_ts"] = time.time()
    detection = dict(state.get("detection") or {})
    detection["bbox_xywh"] = [round(v, 2) for v in state["bbox"]]
    detection["center_px"] = [round(x + float(bbox[2]) / 2.0, 2), round(y + float(bbox[3]) / 2.0, 2)]
    detection["detector"] = "opencv_sparse_lk_tracker_from_yolo_seed"
    detection["confidence"] = round(float(detection.get("confidence") or 0.0) * (0.97 ** state["tracked_frames"]), 4)
    detection["tracking_inliers"] = int(np.count_nonzero(inliers))
    detection["tracked_frames_since_yolo"] = state["tracked_frames"]
    detection["control_boundary"] = "fast_visual_tracking_only_not_motion_permission"
    return detection


def build_fast_tracking_evidence(args: argparse.Namespace, latest_context: dict[str, Any] | None) -> dict[str, Any]:
    if latest_context is None:
        return {"state": "waiting_yolo_seed", "target": None, "end_effector": None}
    frame = read_complete_jpeg_image(Path(args.out_dir) / "latest_left.jpg", cv2.IMREAD_GRAYSCALE)
    if frame is None:
        return {"state": "frame_unavailable", "target": None, "end_effector": None}
    source_frame = int((latest_context.get("capture_loop") or {}).get("frame_index") or 0)
    outputs: dict[str, Any] = {}
    for key, context_key in (("target", "target_object"), ("end_effector", "end_effector_object")):
        state = FAST_TRACK_STATES[key]
        seed = latest_context.get(context_key)
        if isinstance(seed, dict) and state.get("seed_source_frame") != source_frame:
            _seed_fast_tracker(state, frame, seed, source_frame)
            outputs[key] = dict(seed)
        else:
            outputs[key] = _advance_fast_tracker(state, frame)
    target = outputs.get("target")
    effector = outputs.get("end_effector")
    return {
        "schema_version": "opencv_fast_visual_tracking_v1",
        "state": "tracking_pair" if target and effector else ("tracking_partial" if target or effector else "waiting_yolo_seed"),
        "target": target,
        "end_effector": effector,
        "source": "yolo_seed_plus_sparse_lk_optical_flow",
        "control_boundary": "fast_visual_tracking_only_not_motion_permission",
    }


def annotate_fast_tracking(args: argparse.Namespace, evidence: dict[str, Any]) -> None:
    path = Path(args.out_dir) / "latest_left.jpg"
    frame = read_complete_jpeg_image(path)
    if frame is None:
        return
    target = evidence.get("target")
    effector = evidence.get("end_effector")
    if isinstance(target, dict):
        _draw_label_box(frame, target, (0, 220, 255))
    if isinstance(effector, dict):
        _draw_label_box(frame, effector, (255, 190, 40))
    if not isinstance(target, dict) and not isinstance(effector, dict):
        return
    tmp = path.with_name("latest_left.tracking.tmp.jpg")
    if cv2.imwrite(str(tmp), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 72]):
        os.replace(tmp, path)


def build_fast_preview_context(
    args: argparse.Namespace,
    probe_context: dict[str, Any],
    frame_index: int,
    ts: float,
    latest_context: dict[str, Any] | None,
    heavy_every: int,
    heavy_pending: bool,
) -> dict[str, Any]:
    if latest_context is None:
        context: dict[str, Any] = {
            "schema_version": "stereo_rgb_yolo_context_v1",
            "robot_id": args.robot_id,
            "device_id": args.device_id,
            "project_id": args.project_id,
            "left_camera_id": "stereo_left",
            "right_camera_id": "stereo_right",
            "stereo_calibration_id": "",
            "baseline_m": 0.06,
            "image_pair_ref": {
                "left_image_url": f"/api/rehab-arm/v1/devices/{args.device_id}/camera/keyframes/stereo_left/latest/file",
                "right_image_url": f"/api/rehab-arm/v1/devices/{args.device_id}/camera/keyframes/stereo_right/latest/file",
            },
            "detections": {"left": [], "right": []},
            "target_object": None,
            "end_effector_object": None,
            "pixel_servo_hint": {
                "schema_version": "pixel_servo_hint_v1",
                "state": "waiting_detection_context",
                "next_step": "hold_observe",
                "dx_px": None,
                "dy_px": None,
                "distance_px": None,
                "control_boundary": "pixel_servo_hint_only_not_motion_permission",
            },
            "target_quality_gate": {"state": "waiting_async_detector"},
            "right_target_quality_gate": {"state": "waiting_async_detector"},
            "stereo_depth_evidence": {"state": "waiting_async_detector"},
            "estimated_depth_m": None,
            "target_3d_camera_frame": None,
            "camera_to_robot_transform": None,
            "transform_state": "waiting",
            "target_3d_robot_frame": None,
            "end_effector_quality_gate": {"state": "waiting_async_detector"},
            "visual_lock_stability": {"state": "waiting_target_or_end_effector", "stable": False},
            "confidence": 0.0,
            "vla_context": "C++ V fast preview is live; detector context is produced asynchronously.",
            "control_boundary": CONTROL_BOUNDARY,
        }
    else:
        context = dict(latest_context)
    fast_tracking = build_fast_tracking_evidence(args, latest_context)
    annotate_fast_tracking(args, fast_tracking)
    tracked_target = fast_tracking.get("target")
    tracked_effector = fast_tracking.get("end_effector")
    if isinstance(tracked_target, dict):
        context["target_object"] = tracked_target
    if isinstance(tracked_effector, dict):
        context["end_effector_object"] = tracked_effector
    if isinstance(tracked_target, dict) or isinstance(tracked_effector, dict):
        detections = dict(context.get("detections") or {})
        left_detections = [item for item in detections.get("left", []) if isinstance(item, dict)]
        tracked_labels = {_label_of(item) for item in (tracked_target, tracked_effector) if isinstance(item, dict)}
        left_detections = [item for item in left_detections if _label_of(item) not in tracked_labels]
        detections["left"] = [item for item in (tracked_target, tracked_effector) if isinstance(item, dict)] + left_detections
        context["detections"] = detections
    context["fast_visual_tracking"] = fast_tracking
    target_center = detection_center_px(tracked_target)
    effector_center = detection_center_px(tracked_effector)
    if target_center and effector_center:
        dx = round(target_center[0] - effector_center[0], 2)
        dy = round(target_center[1] - effector_center[1], 2)
        context["pixel_servo_hint"] = {
            "schema_version": "pixel_servo_hint_v1",
            "state": "fast_visual_tracking_adjust",
            "next_step": "dry_run_move_right" if dx > 0 else "dry_run_move_left",
            "dx_px": dx,
            "dy_px": dy,
            "distance_px": round(float(np.hypot(dx, dy)), 2),
            "source": "opencv_sparse_lk_tracker_from_yolo_seed",
            "control_boundary": "pixel_servo_hint_only_not_motion_permission",
        }
    capture_loop = dict(context.get("capture_loop") or {})
    capture_loop.update(
        {
            "schema_version": "vla_vision_capture_loop_v1",
            "frame_index": frame_index,
            "process_ms": probe_context.get("process_ms"),
            "mode": "cpp_dual_camera_probe_async_detector",
            "fast_preview_only": True,
            "heavy_context_every_n_frames": heavy_every,
            "heavy_context_pending": heavy_pending,
            "image_orientation": {
                "left_flip": args.left_flip,
                "right_flip": args.right_flip,
                "applied_before_detection": True,
            },
            "camera_mapping": {
                "schema_version": "stereo_camera_mapping_v1",
                "mapping_state": "confirmed_from_nanopi_process_cmdline_and_visual_parallax",
                "logical_left": {
                    "camera_id": "stereo_left",
                    "device_path": args.left,
                    "flip": args.left_flip,
                    "flip_applied_before_detection": True,
                },
                "logical_right": {
                    "camera_id": "stereo_right",
                    "device_path": args.right,
                    "flip": args.right_flip,
                    "flip_applied_before_detection": True,
                },
                "control_boundary": "camera_mapping_evidence_only_not_motion_permission",
            },
            "control_boundary": "capture_loop_only_not_motion_permission",
        }
    )
    context.update(
        {
            "robot_id": args.robot_id,
            "device_id": args.device_id,
            "project_id": args.project_id,
            "frame_ts_unix": ts,
            "capture_loop": capture_loop,
            "scene_summary": (
                "fast stereo preview; async detector is running"
                if heavy_pending
                else "fast stereo preview; latest async detection context retained"
            ),
        }
    )
    return context


def upload_frame_bundle(
    args: argparse.Namespace,
    frame_index: int,
    ts: float,
    context: dict[str, Any],
    left_bytes: bytes,
    right_bytes: bytes,
    upload_right: bool,
    right_upload_every: int,
) -> dict[str, Any]:
    upload_start = time.time()
    context = json.loads(json.dumps(context, ensure_ascii=False))
    common_fields = {
        "robot_id": args.robot_id,
        "project_id": args.project_id,
        "frame_ts_unix": str(ts),
        "image_format": "jpg",
        "width": "640",
        "height": "480",
        "detection_summary": context["scene_summary"],
        "scene_summary": context["scene_summary"],
        "vla_context": context["vla_context"],
    }
    upload_jobs = [
        (
            {**common_fields, "camera_id": "stereo_left", "sha256": hashlib.sha256(left_bytes).hexdigest()},
            left_bytes,
            "stereo_left.jpg",
        )
    ]
    if upload_right:
        upload_jobs.append(
            (
                {**common_fields, "camera_id": "stereo_right", "sha256": hashlib.sha256(right_bytes).hexdigest()},
                right_bytes,
                "stereo_right.jpg",
            )
        )
    with ThreadPoolExecutor(max_workers=len(upload_jobs)) as executor:
        futures = [
            executor.submit(upload_keyframe, args.api_base, args.device_id, fields, image_bytes, file_name)
            for fields, image_bytes, file_name in upload_jobs
        ]
        for future in futures:
            future.result()
    capture_loop = context.setdefault("capture_loop", {})
    capture_loop["upload_ms"] = round((time.time() - upload_start) * 1000.0, 2)
    capture_loop["right_uploaded"] = upload_right
    capture_loop["right_upload_every_n_frames"] = right_upload_every
    capture_loop["upload_completed_frame"] = frame_index
    post_json(f"{args.api_base.rstrip('/')}/api/rehab-arm/v1/devices/{args.device_id}/vision/stereo-context", context)
    return {
        "frame_index": frame_index,
        "upload_ms": capture_loop["upload_ms"],
        "right_uploaded": upload_right,
        "frame_ts_unix": ts,
    }


def main() -> int:
    args = parse_args()
    period = 1.0 / max(args.fps, 0.1)
    heavy_every = max(1, int(args.heavy_every))
    right_upload_every = max(1, int(args.right_upload_every))
    latest_context: dict[str, Any] | None = None
    heavy_future: Future[dict[str, Any]] | None = None
    upload_future: Future[dict[str, Any]] | None = None
    heavy_submitted_frame = 0
    for frame_index in range(1, args.max_frames + 1 if args.max_frames else 1_000_000_000):
        loop_start = time.time()
        try:
            probe_context = run_probe(args)
            ts = time.time()
            completed_upload: dict[str, Any] | None = None
            if upload_future is not None and upload_future.done():
                try:
                    completed_upload = upload_future.result()
                except Exception as exc:
                    print(f"[cpp-upload] async upload failed: {exc}")
                upload_future = None
            completed_heavy = False
            if heavy_future is not None and heavy_future.done():
                try:
                    latest_context = heavy_future.result()
                    completed_heavy = True
                except Exception as exc:
                    print(f"[cpp-upload] async heavy failed: {exc}")
                heavy_future = None
            should_run_heavy = frame_index == 1 or frame_index % heavy_every == 0 or latest_context is None
            submitted_heavy = False
            if should_run_heavy and heavy_future is None:
                heavy_submitted_frame = frame_index
                heavy_future = HEAVY_EXECUTOR.submit(build_stereo_context, args, dict(probe_context), frame_index, ts)
                submitted_heavy = True
            context = build_fast_preview_context(
                args,
                probe_context,
                frame_index,
                ts,
                latest_context,
                heavy_every,
                heavy_future is not None,
            )
            if completed_heavy:
                context.setdefault("capture_loop", {})["async_heavy_completed_frame"] = heavy_submitted_frame
            if submitted_heavy:
                context.setdefault("capture_loop", {})["async_heavy_submitted_frame"] = heavy_submitted_frame
            if completed_upload:
                context.setdefault("capture_loop", {})["async_upload_completed"] = completed_upload
            _write_json_atomic(Path(args.out_dir) / "latest_platform_context.json", context)
            if completed_heavy and latest_context is not None:
                _write_json_atomic(Path(args.out_dir) / "latest_platform_context.json", context)
            if not args.no_upload:
                out_dir = Path(args.out_dir)
                left_bytes = read_complete_jpeg_bytes(out_dir / "latest_left.jpg")
                right_bytes = read_complete_jpeg_bytes(out_dir / "latest_right.jpg")
                upload_right = frame_index == 1 or frame_index % right_upload_every == 0
                if upload_future is None:
                    upload_future = UPLOAD_EXECUTOR.submit(
                        upload_frame_bundle,
                        args,
                        frame_index,
                        ts,
                        context,
                        left_bytes,
                        right_bytes,
                        upload_right,
                        right_upload_every,
                    )
                    context.setdefault("capture_loop", {})["upload_pending"] = True
                    context["capture_loop"]["upload_submitted_frame"] = frame_index
                    context["capture_loop"]["right_uploaded"] = upload_right
                    context["capture_loop"]["right_upload_every_n_frames"] = right_upload_every
                else:
                    context.setdefault("capture_loop", {})["upload_skipped_due_pending"] = True
            print(
                f"[cpp-upload] frame={frame_index} heavy_pending={heavy_future is not None} "
                f"heavy_submitted={submitted_heavy} heavy_completed={completed_heavy} "
                f"target={bool(context.get('target_object'))} process_ms={context['capture_loop']['process_ms']} "
                f"upload_pending={upload_future is not None} upload_done={completed_upload} "
                f"upload_skipped={context['capture_loop'].get('upload_skipped_due_pending', False)} "
                f"loop_ms={round((time.time() - loop_start) * 1000.0, 2)}"
            )
        except Exception as exc:
            print(f"[cpp-upload] loop failed: {exc}")
        sleep_s = period - (time.time() - loop_start)
        if sleep_s > 0:
            time.sleep(sleep_s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
