from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.stereo_camera_capture_upload import (  # noqa: E402
    analyze_stereo_pair_quality,
    build_insmod_command,
    build_stereo_capture_commands,
    make_stereo_frame_paths,
)


class StereoCameraCaptureUploadTests(unittest.TestCase):
    def test_script_has_shebang_for_cmake_ros_executable_install(self) -> None:
        script_path = (
            Path(__file__).resolve().parents[1]
            / 'rehab_arm_psoc_bridge'
            / 'stereo_camera_capture_upload.py'
        )

        self.assertEqual(script_path.read_text(encoding='utf-8').splitlines()[0], '#!/usr/bin/env python3')

    def test_build_insmod_command_uses_existing_module_path(self) -> None:
        command = build_insmod_command('/lib/modules/6.1.141.can-new/kernel/drivers/media/usb/uvc/uvcvideo.ko')

        self.assertEqual(command, ['sudo', 'insmod', '/lib/modules/6.1.141.can-new/kernel/drivers/media/usb/uvc/uvcvideo.ko'])

    def test_build_stereo_capture_commands_use_left_and_right_capture_nodes(self) -> None:
        commands = build_stereo_capture_commands(
            left_device='/dev/video45',
            right_device='/dev/video47',
            left_output='/tmp/left.jpg',
            right_output='/tmp/right.jpg',
            width=640,
            height=480,
            input_format='mjpeg',
        )

        self.assertEqual(len(commands), 2)
        self.assertIn('/dev/video45', commands[0])
        self.assertIn('/tmp/left.jpg', commands[0])
        self.assertIn('/dev/video47', commands[1])
        self.assertIn('/tmp/right.jpg', commands[1])
        self.assertIn('-update', commands[0])
        self.assertIn('640x480', commands[1])

    def test_make_stereo_frame_paths_names_both_sides_for_same_sequence(self) -> None:
        left_path, right_path = make_stereo_frame_paths(
            output_dir=Path('/tmp/frames'),
            robot_id='rehab-arm-alpha',
            device_id='nanopi-m5',
            sequence=7,
            now_struct='20260622T060000Z',
        )

        self.assertEqual(left_path.name, 'rehab-arm-alpha__nanopi-m5__stereo__20260622T060000Z__0007__left.jpg')
        self.assertEqual(right_path.name, 'rehab-arm-alpha__nanopi-m5__stereo__20260622T060000Z__0007__right.jpg')

    def test_analyze_stereo_pair_quality_reports_basic_visual_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            left_path = Path(tmp_dir) / 'left.jpg'
            right_path = Path(tmp_dir) / 'right.jpg'
            left = Image.new('RGB', (4, 4))
            right = Image.new('RGB', (4, 4))
            left.putdata([
                (40 + index * 12, 60 + index * 10, 80 + index * 8)
                for index in range(16)
            ])
            right.putdata([
                (70 + index * 10, 90 + index * 8, 110 + index * 6)
                for index in range(16)
            ])
            left.save(left_path)
            right.save(right_path)

            analysis = analyze_stereo_pair_quality(left_path, right_path)

        self.assertEqual(analysis['left']['width'], 4)
        self.assertEqual(analysis['right']['height'], 4)
        self.assertGreater(analysis['left']['mean_luma'], 0.0)
        self.assertGreater(analysis['pair_difference_mean_abs'], 0.0)
        self.assertTrue(analysis['usable_for_context'])
        self.assertIn('stereo RGB pair', analysis['scene_summary'])

    def test_analyze_stereo_pair_quality_marks_dark_frames_unusable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            left_path = Path(tmp_dir) / 'left.jpg'
            right_path = Path(tmp_dir) / 'right.jpg'
            Image.new('RGB', (4, 4), color=(0, 0, 0)).save(left_path)
            Image.new('RGB', (4, 4), color=(0, 0, 0)).save(right_path)

            analysis = analyze_stereo_pair_quality(left_path, right_path)

        self.assertFalse(analysis['usable_for_context'])
        self.assertIn('too dark', analysis['quality_warnings'])


if __name__ == '__main__':
    unittest.main()
