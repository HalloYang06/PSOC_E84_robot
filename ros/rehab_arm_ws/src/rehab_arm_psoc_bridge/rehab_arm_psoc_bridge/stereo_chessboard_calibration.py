#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.stereo_camera_capture_upload import (
    capture_stereo_frames,
    ensure_uvc_module,
    make_stereo_frame_paths,
)


def parse_chessboard_size(text: str) -> tuple[int, int]:
    parts = text.lower().replace('x', ',').split(',')
    if len(parts) != 2:
        raise ValueError('chessboard size must look like 9x6')
    cols, rows = (int(parts[0]), int(parts[1]))
    if cols <= 1 or rows <= 1:
        raise ValueError('chessboard size is the number of inner corners, both > 1')
    return cols, rows


def find_chessboard_corners(image_path: Path, *, pattern_size: tuple[int, int]) -> dict[str, Any]:
    try:
        import cv2
    except ModuleNotFoundError as exc:
        raise RuntimeError('OpenCV cv2 is required for chessboard calibration') from exc

    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f'OpenCV failed to read image: {image_path}')
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE
    ok, corners = cv2.findChessboardCorners(gray, pattern_size, flags)
    result: dict[str, Any] = {
        'image_path': str(image_path),
        'image_size': [int(gray.shape[1]), int(gray.shape[0])],
        'found': bool(ok),
        'pattern_size': [int(pattern_size[0]), int(pattern_size[1])],
        'corner_count': 0,
    }
    if not ok:
        return result
    criteria = (
        cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
        30,
        0.001,
    )
    refined = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
    points = refined.reshape(-1, 2)
    result.update({
        'corner_count': int(len(points)),
        'first_corner_px': [round(float(points[0][0]), 2), round(float(points[0][1]), 2)],
        'last_corner_px': [round(float(points[-1][0]), 2), round(float(points[-1][1]), 2)],
        'center_corner_px': [
            round(float(points[len(points) // 2][0]), 2),
            round(float(points[len(points) // 2][1]), 2),
        ],
    })
    return result


def analyze_stereo_chessboard_pair(
    left_path: Path,
    right_path: Path,
    *,
    pattern_size: tuple[int, int],
    square_size_m: float,
) -> dict[str, Any]:
    left = find_chessboard_corners(left_path, pattern_size=pattern_size)
    right = find_chessboard_corners(right_path, pattern_size=pattern_size)
    pair_ok = bool(left['found'] and right['found'])
    expected_corners = pattern_size[0] * pattern_size[1]
    return {
        'schema_version': 'stereo_chessboard_observation_v1',
        'frame_ts_unix': time.time(),
        'left': left,
        'right': right,
        'pair_ok': pair_ok,
        'expected_corner_count': expected_corners,
        'square_size_m': square_size_m,
        'teaching_note': (
            'This only verifies that both cameras can see the same calibration board. '
            'Metric depth still requires many accepted board poses and stereo calibration.'
        ),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Capture or inspect a stereo chessboard pair for full stereo calibration preparation.',
    )
    parser.add_argument('--robot-id', default='rehab-arm-alpha')
    parser.add_argument('--device-id', default='nanopi-m5')
    parser.add_argument('--left-device', default='/dev/video45')
    parser.add_argument('--right-device', default='/dev/video47')
    parser.add_argument('--output-dir', default='~/rehab_arm_stereo_calibration')
    parser.add_argument('--width', type=int, default=640)
    parser.add_argument('--height', type=int, default=480)
    parser.add_argument('--input-format', default='mjpeg')
    parser.add_argument('--sequence', type=int, default=1)
    parser.add_argument('--left-image', default='')
    parser.add_argument('--right-image', default='')
    parser.add_argument('--chessboard-size', default='9x6', help='Inner corners, e.g. 9x6.')
    parser.add_argument('--square-size-m', type=float, default=0.025)
    parser.add_argument('--ensure-uvc-module', action='store_true')
    parser.add_argument('--uvc-module-path', default='/lib/modules/6.1.141.can-new/kernel/drivers/media/usb/uvc/uvcvideo.ko')
    parser.add_argument('--pretty', action='store_true')
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    pattern_size = parse_chessboard_size(args.chessboard_size)
    if args.ensure_uvc_module:
        ensure_uvc_module(args.uvc_module_path)
    if args.left_image and args.right_image:
        left_path = Path(args.left_image).expanduser()
        right_path = Path(args.right_image).expanduser()
    else:
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
    report = analyze_stereo_chessboard_pair(
        left_path,
        right_path,
        pattern_size=pattern_size,
        square_size_m=args.square_size_m,
    )
    indent = 2 if args.pretty else None
    print(json.dumps(report, ensure_ascii=False, indent=indent, separators=None if args.pretty else (',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
