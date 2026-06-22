from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


CONTROL_BOUNDARY = 'stereo_vision_context_only_not_motion_permission'
SCHEMA_VERSION = 'stereo_rgb_yolo_context_v1'


def _clamp_confidence(value: float | None) -> float | None:
    if value is None:
        return None
    return min(1.0, max(0.0, float(value)))


def load_detections(text_or_path: str) -> list[dict[str, Any]]:
    source = Path(text_or_path).expanduser()
    text = source.read_text(encoding='utf-8') if source.exists() else text_or_path
    parsed = json.loads(text)
    if isinstance(parsed, list):
        detections = parsed
    elif isinstance(parsed, dict) and isinstance(parsed.get('items'), list):
        detections = parsed['items']
    elif isinstance(parsed, dict) and isinstance(parsed.get('detections'), list):
        detections = parsed['detections']
    else:
        raise ValueError('detections must be a JSON list or an object with items/detections list')
    if not all(isinstance(item, dict) for item in detections):
        raise ValueError('each detection must be a JSON object')
    return [dict(item) for item in detections]


def build_stereo_vision_context_payload(
    *,
    robot_id: str,
    device_id: str,
    project_id: str,
    left_camera_id: str,
    right_camera_id: str,
    left_image_ref: str,
    right_image_ref: str,
    detections: list[dict[str, Any]] | None = None,
    target_object: dict[str, Any] | None = None,
    estimated_depth_m: float | None = None,
    target_3d_camera_frame: dict[str, Any] | None = None,
    baseline_m: float | None = None,
    stereo_calibration_id: str = '',
    scene_summary: str = '',
    vla_context: str = 'two RGB cameras provide approximate depth only; operator must verify before motion',
    confidence: float | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'schema_version': SCHEMA_VERSION,
        'robot_id': robot_id,
        'device_id': device_id,
        'project_id': project_id,
        'frame_ts_unix': time.time() if now is None else now,
        'left_camera_id': left_camera_id,
        'right_camera_id': right_camera_id,
        'stereo_calibration_id': stereo_calibration_id,
        'baseline_m': baseline_m,
        'image_pair_ref': {
            'left_image_url': left_image_ref,
            'right_image_url': right_image_ref,
        },
        'detections': detections or [],
        'target_object': target_object or {},
        'estimated_depth_m': estimated_depth_m,
        'target_3d_camera_frame': target_3d_camera_frame or {},
        'scene_summary': scene_summary,
        'vla_context': vla_context,
        'confidence': _clamp_confidence(confidence),
        'control_boundary': CONTROL_BOUNDARY,
    }
    return payload


def _post_payload(api_base: str, payload: dict[str, Any], token: str = '', timeout_sec: float = 10.0) -> dict[str, Any]:
    import requests

    api_base = api_base.rstrip('/')
    device_id = payload['device_id']
    url = f'{api_base}/api/rehab-arm/v1/devices/{device_id}/vision/stereo-context'
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    response = requests.post(url, headers=headers, json=payload, timeout=timeout_sec)
    response.raise_for_status()
    return response.json()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Build or upload a perception-only stereo RGB context for rehab-arm VLA-V.',
    )
    parser.add_argument('--robot-id', default='rehab-arm-alpha')
    parser.add_argument('--device-id', default='nanopi-m5')
    parser.add_argument('--project-id', default='')
    parser.add_argument('--left-camera-id', default='left_rgb')
    parser.add_argument('--right-camera-id', default='right_rgb')
    parser.add_argument('--left-image-ref', required=True)
    parser.add_argument('--right-image-ref', required=True)
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
    parser.add_argument('--output', default='')
    parser.add_argument('--pretty', action='store_true')
    parser.add_argument('--upload', action='store_true')
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    detections = load_detections(args.detections_json)
    target_object = (
        {'label': args.target_label, 'confidence': _clamp_confidence(args.target_confidence)}
        if args.target_label
        else {}
    )
    payload = build_stereo_vision_context_payload(
        robot_id=args.robot_id,
        device_id=args.device_id,
        project_id=args.project_id,
        left_camera_id=args.left_camera_id,
        right_camera_id=args.right_camera_id,
        left_image_ref=args.left_image_ref,
        right_image_ref=args.right_image_ref,
        detections=detections,
        target_object=target_object,
        estimated_depth_m=args.estimated_depth_m,
        baseline_m=args.baseline_m,
        stereo_calibration_id=args.stereo_calibration_id,
        scene_summary=args.scene_summary,
        vla_context=args.vla_context,
        confidence=args.confidence,
    )
    indent = 2 if args.pretty else None
    text = json.dumps(payload, ensure_ascii=False, indent=indent, separators=None if args.pretty else (',', ':'))
    if args.output:
        Path(args.output).expanduser().write_text(text + '\n', encoding='utf-8')
    else:
        print(text)
    if args.upload:
        if not args.api_base:
            raise SystemExit('--api-base is required with --upload')
        result = _post_payload(args.api_base, payload, args.relay_token)
        print(json.dumps(result, ensure_ascii=False, indent=indent, separators=None if args.pretty else (',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
