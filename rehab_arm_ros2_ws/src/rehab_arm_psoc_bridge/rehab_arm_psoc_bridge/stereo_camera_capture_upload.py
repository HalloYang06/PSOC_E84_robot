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
    parser.add_argument('--estimated-depth-m', type=float)
    parser.add_argument('--baseline-m', type=float)
    parser.add_argument('--stereo-calibration-id', default='')
    parser.add_argument('--scene-summary', default='')
    parser.add_argument('--vla-context', default='two RGB cameras provide approximate depth only; operator must verify before motion')
    parser.add_argument('--confidence', type=float)
    parser.add_argument('--api-base', default='')
    parser.add_argument('--relay-token', default='')
    parser.add_argument('--upload', action='store_true')
    parser.add_argument('--pretty', action='store_true')
    parser.add_argument('--ensure-uvc-module', action='store_true')
    parser.add_argument('--uvc-module-path', default=DEFAULT_UVC_MODULE_PATH)
    return parser


def run_capture_upload(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any] | None]:
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
    target_object = (
        {'label': args.target_label, 'confidence': args.target_confidence}
        if args.target_label
        else {}
    )
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
        scene_summary=args.scene_summary,
        vla_context=args.vla_context,
        confidence=args.confidence,
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
