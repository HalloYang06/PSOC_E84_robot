from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.stereo_chessboard_calibration import (  # noqa: E402
    analyze_stereo_chessboard_pair,
    find_chessboard_corners,
    parse_chessboard_size,
)


class StereoChessboardCalibrationTests(unittest.TestCase):
    def test_parse_chessboard_size_uses_inner_corner_count(self) -> None:
        self.assertEqual(parse_chessboard_size('9x6'), (9, 6))
        self.assertEqual(parse_chessboard_size('7,5'), (7, 5))

    def test_parse_chessboard_size_rejects_invalid_shape(self) -> None:
        with self.assertRaisesRegex(ValueError, 'chessboard size'):
            parse_chessboard_size('9')

    def test_blank_image_reports_no_chessboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / 'blank.jpg'
            Image.new('RGB', (320, 240), color=(255, 255, 255)).save(image_path)

            report = find_chessboard_corners(image_path, pattern_size=(9, 6))

        self.assertFalse(report['found'])
        self.assertEqual(report['corner_count'], 0)
        self.assertEqual(report['image_size'], [320, 240])

    def test_stereo_pair_requires_both_sides_to_find_board(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            left_path = Path(tmp_dir) / 'left.jpg'
            right_path = Path(tmp_dir) / 'right.jpg'
            Image.new('RGB', (320, 240), color=(255, 255, 255)).save(left_path)
            Image.new('RGB', (320, 240), color=(255, 255, 255)).save(right_path)

            report = analyze_stereo_chessboard_pair(
                left_path,
                right_path,
                pattern_size=(9, 6),
                square_size_m=0.025,
            )

        self.assertFalse(report['pair_ok'])
        self.assertEqual(report['expected_corner_count'], 54)
        self.assertEqual(report['square_size_m'], 0.025)


if __name__ == '__main__':
    unittest.main()
