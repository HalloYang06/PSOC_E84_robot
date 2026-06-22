from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.stereo_vision_context import (  # noqa: E402
    build_stereo_vision_context_payload,
    load_detections,
)


class StereoVisionContextTests(unittest.TestCase):
    def test_builds_perception_only_stereo_context_payload(self) -> None:
        payload = build_stereo_vision_context_payload(
            robot_id='rehab-arm-alpha',
            device_id='nanopi-m5',
            project_id='proj-1',
            left_camera_id='left_rgb',
            right_camera_id='right_rgb',
            left_image_ref='/frames/left.jpg',
            right_image_ref='/frames/right.jpg',
            detections=[{'label': 'cup', 'confidence': 0.92}],
            target_object={'label': 'cup', 'confidence': 0.92},
            estimated_depth_m=0.73,
            baseline_m=0.1,
            stereo_calibration_id='bench_calib_001',
            scene_summary='cup on table',
            vla_context='coarse stereo only',
            confidence=1.5,
            now=123.0,
        )

        self.assertEqual(payload['schema_version'], 'stereo_rgb_yolo_context_v1')
        self.assertEqual(payload['left_camera_id'], 'left_rgb')
        self.assertEqual(payload['right_camera_id'], 'right_rgb')
        self.assertEqual(payload['image_pair_ref']['left_image_url'], '/frames/left.jpg')
        self.assertEqual(payload['target_object']['label'], 'cup')
        self.assertEqual(payload['estimated_depth_m'], 0.73)
        self.assertEqual(payload['confidence'], 1.0)
        self.assertEqual(payload['control_boundary'], 'stereo_vision_context_only_not_motion_permission')

    def test_load_detections_accepts_list_or_wrapped_items(self) -> None:
        self.assertEqual(load_detections('[{"label":"hand"}]'), [{'label': 'hand'}])
        self.assertEqual(load_detections('{"items":[{"label":"cup"}]}'), [{'label': 'cup'}])

    def test_load_detections_rejects_non_list_shape(self) -> None:
        with self.assertRaises(ValueError):
            load_detections(json.dumps({'label': 'cup'}))


if __name__ == '__main__':
    unittest.main()
