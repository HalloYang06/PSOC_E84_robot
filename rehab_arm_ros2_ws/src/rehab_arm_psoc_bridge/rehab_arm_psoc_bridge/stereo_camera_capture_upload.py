#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.camera_keyframe_node import build_ffmpeg_capture_command
from rehab_arm_psoc_bridge.data_recording import sanitize_identifier
from rehab_arm_psoc_bridge.stereo_vision_context import (
    _post_payload,
    build_stereo_vision_context_payload,
    load_detections,
)


DEFAULT_UVC_MODULE_PATH = '/lib/modules/6.1.141.can-new/kernel/drivers/media/usb/uvc/uvcvideo.ko'


def _image_pixels(image: Any) -> list[int]:
    if hasattr(image, 'get_flattened_data'):
        return list(image.get_flattened_data())
    return list(image.getdata())


def build_insmod_command(module_path: str) -> list[str]:
    return ['sudo', 'insmod', module_path]


def build_stereo_capture_commands(
    *,
    left_device: str,
    right_device: str,
    left_output: str,
    right_output: str,
    width: int,
    height: int,
    input_format: str,
) -> list[list[str]]:
    return [
        build_ffmpeg_capture_command(
            device=left_device,
            output_path=left_output,
            width=width,
            height=height,
            quality=5,
            input_format=input_format,
        )[:-1] + ['-update', '1', left_output],
        build_ffmpeg_capture_command(
            device=right_device,
            output_path=right_output,
            width=width,
            height=height,
            quality=5,
            input_format=input_format,
        )[:-1] + ['-update', '1', right_output],
    ]


def make_stereo_frame_paths(
    *,
    output_dir: Path,
    robot_id: str,
    device_id: str,
    sequence: int,
    now_struct: str | None = None,
) -> tuple[Path, Path]:
    timestamp = now_struct or time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    session_prefix = sanitize_identifier(f'{robot_id}__{device_id}')
    base_name = f'{session_prefix}__stereo__{timestamp}__{sequence:04d}'
    return output_dir / f'{base_name}__left.jpg', output_dir / f'{base_name}__right.jpg'


def _image_stats(path: Path) -> dict[str, Any]:
    try:
        from PIL import Image
    except ModuleNotFoundError as exc:
        raise RuntimeError('Pillow is required for --analyze-image-quality') from exc

    with Image.open(path) as image:
        gray = image.convert('L')
        width, height = gray.size
        pixels = _image_pixels(gray.resize((min(width, 64), min(height, 64))))
    mean_luma = sum(pixels) / len(pixels) if pixels else 0.0
    adjacent_diffs = [abs(pixels[index] - pixels[index - 1]) for index in range(1, len(pixels))]
    sharpness_proxy = sum(adjacent_diffs) / len(adjacent_diffs) if adjacent_diffs else 0.0
    return {
        'width': width,
        'height': height,
        'mean_luma': round(mean_luma, 2),
        'sharpness_proxy': round(sharpness_proxy, 2),
    }


def _pair_difference(left_path: Path, right_path: Path) -> float:
    try:
        from PIL import Image
    except ModuleNotFoundError as exc:
        raise RuntimeError('Pillow is required for --analyze-image-quality') from exc

    with Image.open(left_path) as left_image, Image.open(right_path) as right_image:
        left_gray = left_image.convert('L').resize((64, 64))
        right_gray = right_image.convert('L').resize((64, 64))
        left_pixels = _image_pixels(left_gray)
        right_pixels = _image_pixels(right_gray)
    return round(sum(abs(a - b) for a, b in zip(left_pixels, right_pixels)) / len(left_pixels), 2)


def analyze_stereo_pair_quality(left_path: Path, right_path: Path) -> dict[str, Any]:
    left = _image_stats(left_path)
    right = _image_stats(right_path)
    pair_difference = _pair_difference(left_path, right_path)
    warnings: list[str] = []
    if min(left['mean_luma'], right['mean_luma']) < 8.0:
        warnings.append('too dark')
    if min(left['sharpness_proxy'], right['sharpness_proxy']) < 1.0:
        warnings.append('low texture or blurred')
    if (left['width'], left['height']) != (right['width'], right['height']):
        warnings.append('left/right resolution mismatch')
    usable = not warnings
    summary = (
        f"stereo RGB pair {left['width']}x{left['height']} captured; "
        f"mean_luma L/R={left['mean_luma']}/{right['mean_luma']}; "
        f"pair_difference={pair_difference}; depth remains uncalibrated"
    )
    return {
        'left': left,
        'right': right,
        'pair_difference_mean_abs': pair_difference,
        'usable_for_context': usable,
        'quality_warnings': warnings,
        'scene_summary': summary,
    }


def detect_visual_region_proposals(image_path: Path, *, max_regions: int = 5) -> list[dict[str, Any]]:
    try:
        import cv2
    except ModuleNotFoundError as exc:
        raise RuntimeError('OpenCV cv2 is required for --detect-visual-regions') from exc

    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f'OpenCV failed to read image: {image_path}')
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 40, 120)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_area = max(64.0, width * height * 0.002)
    proposals: list[dict[str, Any]] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < min_area:
            continue
        x, y, box_width, box_height = cv2.boundingRect(contour)
        if box_width <= 0 or box_height <= 0:
            continue
        confidence = min(0.65, max(0.05, area / float(width * height)))
        proposals.append({
            'label': 'visual_region',
            'confidence': round(confidence, 3),
            'bbox_xywh': [int(x), int(y), int(box_width), int(box_height)],
            'image_ref': str(image_path),
            'source': 'opencv_contour_proposal_not_semantic_detection',
        })
    proposals.sort(key=lambda item: item['bbox_xywh'][2] * item['bbox_xywh'][3], reverse=True)
    return proposals[:max_regions]


def load_label_file(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def _normalize_dnn_output(output: Any) -> Any:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise RuntimeError('numpy is required for YOLO DNN output parsing') from exc

    array = np.asarray(output, dtype=float)
    array = np.squeeze(array)
    if array.ndim == 1:
        array = array.reshape(1, -1)
    if array.ndim != 2:
        raise ValueError(f'YOLO output must reduce to a 2D array, got shape {array.shape}')
    return array


def parse_yolo_dnn_output(
    output: Any,
    *,
    image_width: int,
    image_height: int,
    model_input_width: int | None = None,
    model_input_height: int | None = None,
    labels: list[str],
    confidence_threshold: float,
    nms_threshold: float,
    image_ref: str,
) -> list[dict[str, Any]]:
    try:
        import cv2
    except ModuleNotFoundError as exc:
        raise RuntimeError('OpenCV cv2 is required for YOLO DNN output parsing') from exc

    rows = _normalize_dnn_output(output)
    expected_attribute_counts = {4 + len(labels), 5 + len(labels)}
    if rows.shape[1] not in expected_attribute_counts and rows.shape[0] in expected_attribute_counts:
        rows = rows.T
    boxes: list[list[int]] = []
    confidences: list[float] = []
    class_ids: list[int] = []
    input_width = float(model_input_width or image_width)
    input_height = float(model_input_height or image_height)
    x_scale = float(image_width) / input_width if input_width > 0 else 1.0
    y_scale = float(image_height) / input_height if input_height > 0 else 1.0
    for row in rows:
        if len(row) < 6:
            continue
        cx, cy, box_width, box_height = [float(value) for value in row[:4]]
        scores = row[5:]
        objectness = float(row[4])
        # YOLOv8 ONNX often omits objectness and stores class scores from index 4.
        if objectness > 1.0 or (len(labels) and len(row) == 4 + len(labels)):
            scores = row[4:]
            objectness = 1.0
        class_id = int(scores.argmax()) if hasattr(scores, 'argmax') else max(range(len(scores)), key=lambda idx: scores[idx])
        class_score = float(scores[class_id])
        confidence = objectness * class_score
        if confidence < confidence_threshold:
            continue
        x = int(round((cx - box_width / 2.0) * x_scale))
        y = int(round((cy - box_height / 2.0) * y_scale))
        w = int(round(box_width * x_scale))
        h = int(round(box_height * y_scale))
        x = max(0, min(x, max(0, image_width - 1)))
        y = max(0, min(y, max(0, image_height - 1)))
        w = max(1, min(w, image_width - x))
        h = max(1, min(h, image_height - y))
        boxes.append([x, y, w, h])
        confidences.append(float(confidence))
        class_ids.append(class_id)
    keep = cv2.dnn.NMSBoxes(boxes, confidences, confidence_threshold, nms_threshold)
    if len(keep) == 0:
        return []
    keep_indexes = [int(index) for index in getattr(keep, 'flatten', lambda: keep)()]
    detections = []
    for index in keep_indexes:
        class_id = class_ids[index]
        label = labels[class_id] if 0 <= class_id < len(labels) else f'class_{class_id}'
        detections.append({
            'label': label,
            'confidence': round(confidences[index], 3),
            'bbox_xywh': boxes[index],
            'image_ref': image_ref,
            'source': 'opencv_dnn_yolo',
        })
    detections.sort(key=lambda item: item['confidence'], reverse=True)
    return detections


def detect_yolo_dnn(
    image_path: Path,
    *,
    model_path: Path,
    labels_path: Path,
    input_size: int,
    confidence_threshold: float,
    nms_threshold: float,
) -> list[dict[str, Any]]:
    try:
        import cv2
    except ModuleNotFoundError as exc:
        raise RuntimeError('OpenCV cv2 is required for --yolo-onnx') from exc

    labels = load_label_file(labels_path)
    if not labels:
        raise RuntimeError(f'YOLO label file is empty: {labels_path}')
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f'OpenCV failed to read image: {image_path}')
    height, width = image.shape[:2]
    try:
        net = cv2.dnn.readNetFromONNX(str(model_path))
    except cv2.error as exc:
        raise RuntimeError(
            f'OpenCV DNN failed to load YOLO ONNX model {model_path}; '
            'choose an ONNX export compatible with the NanoPi OpenCV runtime'
        ) from exc
    blob = cv2.dnn.blobFromImage(image, 1.0 / 255.0, (input_size, input_size), swapRB=True, crop=False)
    net.setInput(blob)
    outputs = net.forward()
    return parse_yolo_dnn_output(
        outputs,
        image_width=width,
        image_height=height,
        model_input_width=input_size,
        model_input_height=input_size,
        labels=labels,
        confidence_threshold=confidence_threshold,
        nms_threshold=nms_threshold,
        image_ref=str(image_path),
    )


def parse_ssd_dnn_output(
    output: Any,
    *,
    image_width: int,
    image_height: int,
    labels: list[str],
    confidence_threshold: float,
    image_ref: str,
) -> list[dict[str, Any]]:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise RuntimeError('numpy is required for SSD DNN output parsing') from exc

    detections = np.asarray(output, dtype=float).reshape(-1, 7)
    parsed: list[dict[str, Any]] = []
    for row in detections:
        confidence = float(row[2])
        if confidence < confidence_threshold:
            continue
        class_id = int(row[1])
        label = labels[class_id] if 0 <= class_id < len(labels) else f'class_{class_id}'
        x1 = int(round(row[3] * image_width))
        y1 = int(round(row[4] * image_height))
        x2 = int(round(row[5] * image_width))
        y2 = int(round(row[6] * image_height))
        x = max(0, min(x1, max(0, image_width - 1)))
        y = max(0, min(y1, max(0, image_height - 1)))
        w = max(1, min(x2, image_width) - x)
        h = max(1, min(y2, image_height) - y)
        parsed.append({
            'label': label,
            'confidence': round(confidence, 3),
            'bbox_xywh': [x, y, w, h],
            'image_ref': image_ref,
            'source': 'opencv_dnn_mobilenet_ssd',
        })
    parsed.sort(key=lambda item: item['confidence'], reverse=True)
    return parsed


def detect_ssd_dnn(
    image_path: Path,
    *,
    prototxt_path: Path,
    model_path: Path,
    labels_path: Path,
    confidence_threshold: float,
) -> list[dict[str, Any]]:
    try:
        import cv2
    except ModuleNotFoundError as exc:
        raise RuntimeError('OpenCV cv2 is required for --ssd-model') from exc

    labels = load_label_file(labels_path)
    if not labels:
        raise RuntimeError(f'SSD label file is empty: {labels_path}')
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f'OpenCV failed to read image: {image_path}')
    height, width = image.shape[:2]
    try:
        net = cv2.dnn.readNetFromCaffe(str(prototxt_path), str(model_path))
    except cv2.error as exc:
        raise RuntimeError(
            f'OpenCV DNN failed to load SSD model {model_path}; '
            'choose Caffe MobileNet-SSD assets compatible with the NanoPi OpenCV runtime'
        ) from exc
    blob = cv2.dnn.blobFromImage(image, 0.007843, (300, 300), 127.5)
    net.setInput(blob)
    outputs = net.forward()
    return parse_ssd_dnn_output(
        outputs,
        image_width=width,
        image_height=height,
        labels=labels,
        confidence_threshold=confidence_threshold,
        image_ref=str(image_path),
    )


def validate_detector_args(*, yolo_onnx: str, yolo_labels: str) -> None:
    if yolo_onnx and not yolo_labels:
        raise ValueError('--yolo-labels is required with --yolo-onnx')
    if not yolo_onnx:
        return
    model_path = Path(yolo_onnx).expanduser()
    labels_path = Path(yolo_labels).expanduser()
    if not model_path.is_file():
        raise FileNotFoundError(f'YOLO ONNX model not found: {model_path}')
    if not labels_path.is_file():
        raise FileNotFoundError(f'YOLO labels file not found: {labels_path}')
    if not load_label_file(labels_path):
        raise ValueError(f'YOLO labels file is empty: {labels_path}')


def validate_ssd_args(*, ssd_model: str, ssd_prototxt: str, ssd_labels: str) -> None:
    if not ssd_model and not ssd_prototxt and not ssd_labels:
        return
    if not ssd_model or not ssd_prototxt or not ssd_labels:
        raise ValueError('--ssd-model, --ssd-prototxt, and --ssd-labels must be provided together')
    model_path = Path(ssd_model).expanduser()
    prototxt_path = Path(ssd_prototxt).expanduser()
    labels_path = Path(ssd_labels).expanduser()
    if not model_path.is_file():
        raise FileNotFoundError(f'SSD model not found: {model_path}')
    if not prototxt_path.is_file():
        raise FileNotFoundError(f'SSD prototxt not found: {prototxt_path}')
    if not labels_path.is_file():
        raise FileNotFoundError(f'SSD labels file not found: {labels_path}')
    if not load_label_file(labels_path):
        raise ValueError(f'SSD labels file is empty: {labels_path}')


def _parse_allowlist(text: str) -> set[str]:
    return {item.strip() for item in text.split(',') if item.strip()}


def select_target_object_from_detections(
    detections: list[dict[str, Any]],
    *,
    allowed_labels: set[str] | None = None,
) -> dict[str, Any]:
    allowed = allowed_labels or set()
    candidates = []
    for detection in detections:
        source = str(detection.get('source', ''))
        label = str(detection.get('label', ''))
        if not source.startswith('opencv_dnn_'):
            continue
        if allowed and label not in allowed:
            continue
        try:
            confidence = float(detection.get('confidence', 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        candidates.append((confidence, detection))
    if not candidates:
        return {}
    _, best = max(candidates, key=lambda item: item[0])
    target = {
        'label': str(best.get('label', '')),
        'confidence': float(best.get('confidence', 0.0)),
        'source': best.get('source', ''),
    }
    if 'bbox_xywh' in best:
        target['bbox_xywh'] = best['bbox_xywh']
    if 'image_ref' in best:
        target['image_ref'] = best['image_ref']
    return target


def _run_command(command: list[str], *, timeout_sec: float, allow_already_loaded: bool = False) -> None:
    completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_sec, check=False)
    if completed.returncode == 0:
        return
    text = (completed.stderr or completed.stdout or f'command exited {completed.returncode}').strip()
    if allow_already_loaded and 'File exists' in text:
        return
    raise RuntimeError(text)


def ensure_uvc_module(module_path: str, *, timeout_sec: float = 10.0) -> None:
    _run_command(build_insmod_command(module_path), timeout_sec=timeout_sec, allow_already_loaded=True)


def capture_stereo_frames(
    *,
    left_device: str,
    right_device: str,
    left_output: Path,
    right_output: Path,
    width: int,
    height: int,
    input_format: str,
    timeout_sec: float = 15.0,
) -> tuple[Path, Path]:
    left_output.parent.mkdir(parents=True, exist_ok=True)
    right_output.parent.mkdir(parents=True, exist_ok=True)
    commands = build_stereo_capture_commands(
        left_device=left_device,
        right_device=right_device,
        left_output=str(left_output),
        right_output=str(right_output),
        width=width,
        height=height,
        input_format=input_format,
    )
    for command in commands:
        _run_command(command, timeout_sec=timeout_sec)
    for path in (left_output, right_output):
        if not path.exists() or path.stat().st_size == 0:
            raise RuntimeError(f'capture produced empty file: {path}')
    return left_output, right_output


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Capture two NanoPi USB camera frames and upload a perception-only VLA-V stereo context.',
    )
    parser.add_argument('--robot-id', default='rehab-arm-alpha')
    parser.add_argument('--device-id', default='nanopi-m5')
    parser.add_argument('--project-id', required=True)
    parser.add_argument('--left-device', default='/dev/video45')
    parser.add_argument('--right-device', default='/dev/video47')
    parser.add_argument('--left-camera-id', default='left_rgb')
    parser.add_argument('--right-camera-id', default='right_rgb')
    parser.add_argument('--output-dir', default='~/rehab_arm_stereo_frames')
    parser.add_argument('--width', type=int, default=640)
    parser.add_argument('--height', type=int, default=480)
    parser.add_argument('--input-format', default='mjpeg')
    parser.add_argument('--sequence', type=int, default=1)
    parser.add_argument('--detections-json', default='[]')
    parser.add_argument('--target-label', default='')
    parser.add_argument('--target-confidence', type=float)
    parser.add_argument('--auto-target-from-detections', action='store_true')
    parser.add_argument('--target-label-allowlist', default='')
    parser.add_argument('--estimated-depth-m', type=float)
    parser.add_argument('--baseline-m', type=float)
    parser.add_argument('--stereo-calibration-id', default='')
    parser.add_argument('--scene-summary', default='')
    parser.add_argument('--vla-context', default='two RGB cameras provide approximate depth only; operator must verify before motion')
    parser.add_argument('--confidence', type=float)
    parser.add_argument('--analyze-image-quality', action='store_true')
    parser.add_argument('--detect-visual-regions', action='store_true')
    parser.add_argument('--max-visual-regions', type=int, default=5)
    parser.add_argument('--yolo-onnx', default='')
    parser.add_argument('--yolo-labels', default='')
    parser.add_argument('--yolo-input-size', type=int, default=640)
    parser.add_argument('--yolo-confidence-threshold', type=float, default=0.35)
    parser.add_argument('--yolo-nms-threshold', type=float, default=0.45)
    parser.add_argument('--ssd-model', default='')
    parser.add_argument('--ssd-prototxt', default='')
    parser.add_argument('--ssd-labels', default='')
    parser.add_argument('--ssd-confidence-threshold', type=float, default=0.35)
    parser.add_argument('--api-base', default='')
    parser.add_argument('--relay-token', default='')
    parser.add_argument('--upload', action='store_true')
    parser.add_argument('--pretty', action='store_true')
    parser.add_argument('--ensure-uvc-module', action='store_true')
    parser.add_argument('--uvc-module-path', default=DEFAULT_UVC_MODULE_PATH)
    return parser


def run_capture_upload(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any] | None]:
    validate_detector_args(yolo_onnx=args.yolo_onnx, yolo_labels=args.yolo_labels)
    validate_ssd_args(ssd_model=args.ssd_model, ssd_prototxt=args.ssd_prototxt, ssd_labels=args.ssd_labels)
    if args.ensure_uvc_module:
        ensure_uvc_module(args.uvc_module_path)
    output_dir = Path(args.output_dir).expanduser()
    left_path, right_path = make_stereo_frame_paths(
        output_dir=output_dir,
        robot_id=args.robot_id,
        device_id=args.device_id,
        sequence=args.sequence,
    )
    capture_stereo_frames(
        left_device=args.left_device,
        right_device=args.right_device,
        left_output=left_path,
        right_output=right_path,
        width=args.width,
        height=args.height,
        input_format=args.input_format,
    )
    detections = load_detections(args.detections_json)
    quality_analysis = analyze_stereo_pair_quality(left_path, right_path) if args.analyze_image_quality else None
    if args.detect_visual_regions:
        detections = detections + detect_visual_region_proposals(left_path, max_regions=max(1, args.max_visual_regions))
    if args.yolo_onnx:
        detections = detections + detect_yolo_dnn(
            left_path,
            model_path=Path(args.yolo_onnx).expanduser(),
            labels_path=Path(args.yolo_labels).expanduser(),
            input_size=args.yolo_input_size,
            confidence_threshold=args.yolo_confidence_threshold,
            nms_threshold=args.yolo_nms_threshold,
        )
    if args.ssd_model:
        detections = detections + detect_ssd_dnn(
            left_path,
            prototxt_path=Path(args.ssd_prototxt).expanduser(),
            model_path=Path(args.ssd_model).expanduser(),
            labels_path=Path(args.ssd_labels).expanduser(),
            confidence_threshold=args.ssd_confidence_threshold,
        )
    target_object = (
        {'label': args.target_label, 'confidence': args.target_confidence}
        if args.target_label
        else {}
    )
    if not target_object and args.auto_target_from_detections:
        target_object = select_target_object_from_detections(
            detections,
            allowed_labels=_parse_allowlist(args.target_label_allowlist),
        )
    scene_summary = args.scene_summary
    confidence = args.confidence
    vla_context = args.vla_context
    if quality_analysis is not None:
        scene_summary = scene_summary or quality_analysis['scene_summary']
        confidence = confidence if confidence is not None else (0.55 if quality_analysis['usable_for_context'] else 0.15)
        vla_context = (
            f"{vla_context}; image_quality={json.dumps(quality_analysis, ensure_ascii=False, separators=(',', ':'))}"
        )
    if args.detect_visual_regions:
        vla_context = f'{vla_context}; detections include class-agnostic visual region proposals, not semantic YOLO labels'
    if args.yolo_onnx:
        vla_context = f'{vla_context}; semantic detections generated by OpenCV DNN YOLO ONNX'
    if args.ssd_model:
        vla_context = f'{vla_context}; semantic detections generated by OpenCV DNN MobileNet-SSD'
    if target_object and args.auto_target_from_detections:
        vla_context = f"{vla_context}; target_object selected from semantic detections only"
    payload = build_stereo_vision_context_payload(
        robot_id=args.robot_id,
        device_id=args.device_id,
        project_id=args.project_id,
        left_camera_id=args.left_camera_id,
        right_camera_id=args.right_camera_id,
        left_image_ref=str(left_path),
        right_image_ref=str(right_path),
        detections=detections,
        target_object=target_object,
        estimated_depth_m=args.estimated_depth_m,
        baseline_m=args.baseline_m,
        stereo_calibration_id=args.stereo_calibration_id,
        scene_summary=scene_summary,
        vla_context=vla_context,
        confidence=confidence,
    )
    result = None
    if args.upload:
        if not args.api_base:
            raise RuntimeError('--api-base is required with --upload')
        result = _post_payload(args.api_base, payload, args.relay_token)
    return payload, result


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    payload, result = run_capture_upload(args)
    indent = 2 if args.pretty else None
    print(json.dumps(payload, ensure_ascii=False, indent=indent, separators=None if args.pretty else (',', ':')))
    if result is not None:
        print(json.dumps(result, ensure_ascii=False, indent=indent, separators=None if args.pretty else (',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
