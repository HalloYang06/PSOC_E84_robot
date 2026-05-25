from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.camera_keyframe_node import build_ffmpeg_capture_command  # noqa: E402


class CameraKeyframeNodeTests(unittest.TestCase):
    def test_build_ffmpeg_capture_command_defaults_to_v4l2_jpeg_frame(self) -> None:
        command = build_ffmpeg_capture_command(
            device='/dev/video0',
            output_path='/tmp/frame.jpg',
            width=640,
            height=480,
            quality=5,
        )

        self.assertEqual(command[0], 'ffmpeg')
        self.assertIn('-f', command)
        self.assertIn('v4l2', command)
        self.assertIn('640x480', command)
        self.assertIn('/dev/video0', command)
        self.assertEqual(command[-1], '/tmp/frame.jpg')

    def test_build_ffmpeg_capture_command_allows_input_format(self) -> None:
        command = build_ffmpeg_capture_command(
            device='/dev/video2',
            output_path='/tmp/frame.jpg',
            width=320,
            height=240,
            quality=7,
            input_format='mjpeg',
        )

        self.assertIn('-input_format', command)
        self.assertIn('mjpeg', command)
        self.assertIn('320x240', command)


if __name__ == '__main__':
    unittest.main()
