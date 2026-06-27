from __future__ import annotations

import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import numpy as np
from PIL import Image


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.stereo_camera_capture_upload import (  # noqa: E402
    analyze_stereo_pair_quality,
    build_insmod_command,
    build_stereo_capture_commands,
    build_stereo_observation_for_target,
    detect_yolo_dnn,
    detect_visual_region_proposals,
    load_label_file,
    parse_ssd_dnn_output,
    make_stereo_frame_paths,
    parse_yolo_dnn_output,
    select_target_object_from_detections,
    validate_detector_args,
    validate_ssd_args,
)


class StereoCameraCaptureUploadTests(unittest.TestCase):
    def test_script_has_shebang_for_cmake_ros_executable_install(self) -> None:
        script_path = (
            Path(__file__).resolve().parents[1]
            / 'rehab_arm_psoc_bridge'
            / 'stereo_camera_capture_upload.py'
        )

        self.assertEqual(script_path.read_text(encoding='utf-8').splitlines()[0], '#!/usr/bin/env python3')

    def test_cpp_stereo_capture_executable_is_installed_by_cmake(self) -> None:
        package_root = Path(__file__).resolve().parents[1]
        source_path = package_root / 'src' / 'stereo_camera_capture_upload_cpp.cpp'
        cmake_text = (package_root / 'CMakeLists.txt').read_text(encoding='utf-8')

        self.assertTrue(source_path.is_file())
        self.assertIn('find_package(OpenCV REQUIRED)', cmake_text)
        self.assertIn('add_executable(stereo_camera_capture_upload_cpp', cmake_text)
        self.assertIn('install(TARGETS', cmake_text)
        self.assertIn('stereo_camera_capture_upload_cpp', cmake_text)

    def test_cpp_stereo_capture_keeps_one_shot_default_and_optional_loop_mode(self) -> None:
        package_root = Path(__file__).resolve().parents[1]
        source_text = (package_root / 'src' / 'stereo_camera_capture_upload_cpp.cpp').read_text(encoding='utf-8')

        self.assertIn('int loop_count = 1;', source_text)
        self.assertIn('--loop-count', source_text)
        self.assertIn('--interval-ms', source_text)
        self.assertIn('options.sequence + index', source_text)
        self.assertIn('std::this_thread::sleep_for', source_text)

    def test_cpp_stereo_capture_payload_includes_loop_telemetry(self) -> None:
        package_root = Path(__file__).resolve().parents[1]
        source_text = (package_root / 'src' / 'stereo_camera_capture_upload_cpp.cpp').read_text(encoding='utf-8')

        self.assertIn('struct LoopTelemetry', source_text)
        self.assertIn('capture_loop', source_text)
        self.assertIn('loop_index', source_text)
        self.assertIn('frame_process_ms', source_text)
        self.assertIn('loop_elapsed_ms', source_text)

    def test_cpp_stereo_capture_payload_includes_uncalibrated_pixel_servo_hint(self) -> None:
        package_root = Path(__file__).resolve().parents[1]
        source_text = (package_root / 'src' / 'stereo_camera_capture_upload_cpp.cpp').read_text(encoding='utf-8')

        self.assertIn('pixel_servo_hint_json', source_text)
        self.assertIn('uncalibrated_pixel_servo_hint_v1', source_text)
        self.assertIn('pixel_servo_hint_only_not_motion_permission', source_text)
        self.assertIn('dry_run_shift_left', source_text)
        self.assertIn('metric_depth_available', source_text)

    def test_cpp_stereo_capture_supports_yolox_onnx_detector(self) -> None:
        package_root = Path(__file__).resolve().parents[1]
        source_text = (package_root / 'src' / 'stereo_camera_capture_upload_cpp.cpp').read_text(encoding='utf-8')

        self.assertIn('--yolox-onnx', source_text)
        self.assertIn('detect_yolox', source_text)
        self.assertIn('readNetFromONNX', source_text)
        self.assertIn('opencv_dnn_yolox', source_text)
        self.assertIn('cv::dnn::NMSBoxes', source_text)

    def test_stereo_upload_loop_uses_persistent_cpp_process(self) -> None:
        repo_root = Path(__file__).resolve().parents[4]
        script_text = (repo_root / 'scripts' / 'nanopi_stereo_vla_upload_loop.sh').read_text(encoding='utf-8')

        self.assertIn('run_cpp_loop_once()', script_text)
        self.assertIn('--loop-count "$COUNT"', script_text)
        self.assertIn('--interval-ms "$INTERVAL_MS"', script_text)
        self.assertIn('if [ "$VISION_IMPL" = "cpp" ]; then', script_text)
        self.assertIn('run_cpp_loop_once', script_text)

    def test_stereo_upload_loop_can_enable_yolox_for_cpp_detector(self) -> None:
        repo_root = Path(__file__).resolve().parents[4]
        script_text = (repo_root / 'scripts' / 'nanopi_stereo_vla_upload_loop.sh').read_text(encoding='utf-8')

        self.assertIn('USE_YOLOX="${USE_YOLOX:-1}"', script_text)
        self.assertIn('YOLOX_MODEL="${YOLOX_MODEL:-/home/pi/rehab_arm_models/yolo/yolox_nano.onnx}"', script_text)
        self.assertIn('--yolox-onnx "$YOLOX_MODEL"', script_text)
        self.assertIn('--detect-right-yolox', script_text)

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

    def test_build_stereo_capture_commands_can_rotate_both_images_180_degrees(self) -> None:
        commands = build_stereo_capture_commands(
            left_device='/dev/video45',
            right_device='/dev/video47',
            left_output='/tmp/left.jpg',
            right_output='/tmp/right.jpg',
            width=640,
            height=480,
            input_format='mjpeg',
            rotate_180=True,
        )

        self.assertIn('-vf', commands[0])
        self.assertIn('transpose=2,transpose=2', commands[0])
        self.assertIn('-vf', commands[1])
        self.assertLess(commands[0].index('-vf'), commands[0].index('/tmp/left.jpg'))
        self.assertLess(commands[1].index('-vf'), commands[1].index('/tmp/right.jpg'))

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

    def test_detect_visual_region_proposals_returns_bounding_boxes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / 'left.jpg'
            image = Image.new('RGB', (80, 60), color=(20, 20, 20))
            for y in range(15, 45):
                for x in range(20, 55):
                    image.putpixel((x, y), (220, 220, 220))
            image.save(image_path)

            detections = detect_visual_region_proposals(image_path, max_regions=3)

        self.assertGreaterEqual(len(detections), 1)
        first = detections[0]
        self.assertEqual(first['label'], 'visual_region')
        self.assertEqual(first['source'], 'opencv_contour_proposal_not_semantic_detection')
        self.assertGreater(first['confidence'], 0.0)
        self.assertGreater(first['bbox_xywh'][2], 0)
        self.assertGreater(first['bbox_xywh'][3], 0)

    def test_load_label_file_ignores_blank_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            labels_path = Path(tmp_dir) / 'labels.txt'
            labels_path.write_text('person\n\ncup\n', encoding='utf-8')

            labels = load_label_file(labels_path)

        self.assertEqual(labels, ['person', 'cup'])

    def test_parse_yolo_dnn_output_converts_center_boxes_to_detections(self) -> None:
        # Row layout: cx, cy, width, height, objectness, class0, class1.
        output = np.array([
            [320.0, 240.0, 160.0, 120.0, 0.9, 0.1, 0.8],
            [20.0, 20.0, 10.0, 10.0, 0.3, 0.9, 0.1],
        ], dtype=np.float32)

        detections = parse_yolo_dnn_output(
            output,
            image_width=640,
            image_height=480,
            labels=['person', 'cup'],
            confidence_threshold=0.5,
            nms_threshold=0.4,
            image_ref='/tmp/left.jpg',
        )

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0]['label'], 'cup')
        self.assertAlmostEqual(detections[0]['confidence'], 0.72, places=2)
        self.assertEqual(detections[0]['bbox_xywh'], [240, 180, 160, 120])
        self.assertEqual(detections[0]['source'], 'opencv_dnn_yolo')

    def test_parse_yolo_dnn_output_handles_yolov8_transposed_shape(self) -> None:
        # Shape is attributes x predictions: 4 box values + 2 class scores.
        output = np.array([
            [100.0, 300.0],
            [80.0, 200.0],
            [50.0, 80.0],
            [40.0, 60.0],
            [0.8, 0.1],
            [0.2, 0.9],
        ], dtype=np.float32)

        detections = parse_yolo_dnn_output(
            output,
            image_width=640,
            image_height=480,
            labels=['hand', 'cup'],
            confidence_threshold=0.5,
            nms_threshold=0.4,
            image_ref='/tmp/left.jpg',
        )

        self.assertEqual([item['label'] for item in detections], ['cup', 'hand'])

    def test_parse_yolo_dnn_output_scales_model_coordinates_to_image_size(self) -> None:
        output = np.array([
            [320.0, 240.0, 160.0, 120.0, 0.9, 0.8, 0.1],
        ], dtype=np.float32)

        detections = parse_yolo_dnn_output(
            output,
            image_width=320,
            image_height=240,
            model_input_width=640,
            model_input_height=480,
            labels=['hand', 'cup'],
            confidence_threshold=0.5,
            nms_threshold=0.4,
            image_ref='/tmp/left.jpg',
        )

        self.assertEqual(detections[0]['bbox_xywh'], [120, 90, 80, 60])

    def test_validate_detector_args_requires_labels_with_yolo_model(self) -> None:
        with self.assertRaisesRegex(ValueError, '--yolo-labels is required'):
            validate_detector_args(yolo_onnx='/tmp/model.onnx', yolo_labels='')

    def test_validate_detector_args_checks_model_and_label_files_before_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            labels_path = Path(tmp_dir) / 'labels.txt'
            labels_path.write_text('cup\n', encoding='utf-8')

            with self.assertRaisesRegex(FileNotFoundError, 'YOLO ONNX model not found'):
                validate_detector_args(yolo_onnx=str(Path(tmp_dir) / 'missing.onnx'), yolo_labels=str(labels_path))

    def test_validate_detector_args_rejects_empty_label_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            model_path = Path(tmp_dir) / 'model.onnx'
            labels_path = Path(tmp_dir) / 'labels.txt'
            model_path.write_bytes(b'not a real onnx, only path validation')
            labels_path.write_text('\n', encoding='utf-8')

            with self.assertRaisesRegex(ValueError, 'YOLO labels file is empty'):
                validate_detector_args(yolo_onnx=str(model_path), yolo_labels=str(labels_path))

    def test_detect_yolo_dnn_wraps_opencv_model_load_errors(self) -> None:
        import cv2

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / 'left.jpg'
            model_path = Path(tmp_dir) / 'model.onnx'
            labels_path = Path(tmp_dir) / 'labels.txt'
            Image.new('RGB', (8, 8), color=(20, 20, 20)).save(image_path)
            model_path.write_bytes(b'not a real onnx')
            labels_path.write_text('cup\n', encoding='utf-8')

            with mock.patch.object(cv2.dnn, 'readNetFromONNX', side_effect=cv2.error('bad onnx')):
                with self.assertRaisesRegex(RuntimeError, 'OpenCV DNN failed to load YOLO ONNX model'):
                    detect_yolo_dnn(
                        image_path,
                        model_path=model_path,
                        labels_path=labels_path,
                        input_size=640,
                        confidence_threshold=0.25,
                        nms_threshold=0.45,
                    )

    def test_parse_ssd_dnn_output_converts_normalized_boxes(self) -> None:
        output = np.array([[[[
            [0.0, 15.0, 0.8, 0.25, 0.25, 0.75, 0.5],
            [0.0, 7.0, 0.2, 0.1, 0.1, 0.2, 0.2],
        ]]]], dtype=np.float32)
        labels = [f'class_{index}' for index in range(21)]
        labels[15] = 'person'

        detections = parse_ssd_dnn_output(
            output,
            image_width=640,
            image_height=480,
            labels=labels,
            confidence_threshold=0.35,
            image_ref='/tmp/left.jpg',
        )

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0]['label'], 'person')
        self.assertEqual(detections[0]['bbox_xywh'], [160, 120, 320, 120])
        self.assertEqual(detections[0]['image_side'], 'left')
        self.assertEqual(detections[0]['source'], 'opencv_dnn_mobilenet_ssd')

    def test_validate_ssd_args_requires_complete_asset_triplet(self) -> None:
        with self.assertRaisesRegex(ValueError, '--ssd-model, --ssd-prototxt, and --ssd-labels'):
            validate_ssd_args(ssd_model='/tmp/model.caffemodel', ssd_prototxt='', ssd_labels='')

    def test_validate_ssd_args_checks_files_before_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            model_path = Path(tmp_dir) / 'model.caffemodel'
            labels_path = Path(tmp_dir) / 'labels.txt'
            model_path.write_bytes(b'not a real caffe model, only path validation')
            labels_path.write_text('background\nperson\n', encoding='utf-8')

            with self.assertRaisesRegex(FileNotFoundError, 'SSD prototxt not found'):
                validate_ssd_args(
                    ssd_model=str(model_path),
                    ssd_prototxt=str(Path(tmp_dir) / 'missing.prototxt'),
                    ssd_labels=str(labels_path),
                )

    def test_select_target_object_from_detections_uses_highest_confidence_semantic_detection(self) -> None:
        target = select_target_object_from_detections([
            {'label': 'visual_region', 'confidence': 0.99, 'source': 'opencv_contour_proposal_not_semantic_detection'},
            {'label': 'diningtable', 'confidence': 0.67, 'bbox_xywh': [1, 2, 3, 4], 'source': 'opencv_dnn_mobilenet_ssd'},
            {'label': 'bottle', 'confidence': 0.995, 'bbox_xywh': [5, 6, 7, 8], 'source': 'opencv_dnn_mobilenet_ssd'},
        ])

        self.assertEqual(target['label'], 'bottle')
        self.assertEqual(target['bbox_xywh'], [5, 6, 7, 8])
        self.assertEqual(target['source'], 'opencv_dnn_mobilenet_ssd')

    def test_select_target_object_from_detections_uses_left_image_semantic_detection_only(self) -> None:
        target = select_target_object_from_detections([
            {
                'label': 'chair',
                'confidence': 0.9,
                'bbox_xywh': [10, 10, 30, 40],
                'image_side': 'right',
                'source': 'opencv_dnn_mobilenet_ssd',
            },
            {
                'label': 'bottle',
                'confidence': 0.7,
                'bbox_xywh': [100, 120, 20, 60],
                'image_side': 'left',
                'source': 'opencv_dnn_mobilenet_ssd',
            },
        ])

        self.assertEqual(target['label'], 'bottle')
        self.assertEqual(target['image_side'], 'left')

    def test_build_stereo_observation_for_target_matches_right_detection(self) -> None:
        target = {
            'label': 'bottle',
            'confidence': 0.99,
            'bbox_xywh': [280, 5, 100, 320],
            'source': 'opencv_dnn_mobilenet_ssd',
            'image_side': 'left',
        }
        observation = build_stereo_observation_for_target(target, [
            target,
            {
                'label': 'bottle',
                'confidence': 0.94,
                'bbox_xywh': [170, 8, 110, 318],
                'source': 'opencv_dnn_mobilenet_ssd',
                'image_side': 'right',
            },
            {
                'label': 'diningtable',
                'confidence': 0.98,
                'bbox_xywh': [0, 300, 640, 120],
                'source': 'opencv_dnn_mobilenet_ssd',
                'image_side': 'right',
            },
        ])

        self.assertEqual(observation['label'], 'bottle')
        self.assertEqual(observation['left_bbox_xywh'], [280, 5, 100, 320])
        self.assertEqual(observation['right_bbox_xywh'], [170, 8, 110, 318])
        self.assertEqual(observation['depth_status'], 'uncalibrated_pixel_disparity_only')
        self.assertGreater(observation['horizontal_disparity_px'], 0)

    def test_build_stereo_observation_rejects_large_vertical_mismatch(self) -> None:
        target = {
            'label': 'bottle',
            'bbox_xywh': [280, 5, 100, 320],
            'source': 'opencv_dnn_mobilenet_ssd',
            'image_side': 'left',
        }
        observation = build_stereo_observation_for_target(
            target,
            [{
                'label': 'bottle',
                'confidence': 0.94,
                'bbox_xywh': [170, 300, 110, 80],
                'source': 'opencv_dnn_mobilenet_ssd',
                'image_side': 'right',
            }],
            max_vertical_center_delta_px=40.0,
        )

        self.assertEqual(observation, {})

    def test_select_target_object_from_detections_honors_allowlist(self) -> None:
        target = select_target_object_from_detections(
            [
                {'label': 'diningtable', 'confidence': 0.99, 'source': 'opencv_dnn_mobilenet_ssd'},
                {'label': 'bottle', 'confidence': 0.8, 'source': 'opencv_dnn_mobilenet_ssd'},
            ],
            allowed_labels={'bottle'},
        )

        self.assertEqual(target['label'], 'bottle')

    def test_select_target_object_from_detections_returns_empty_without_semantic_match(self) -> None:
        target = select_target_object_from_detections([
            {'label': 'visual_region', 'confidence': 0.99, 'source': 'opencv_contour_proposal_not_semantic_detection'},
            {'label': 'bottle', 'confidence': 0.8, 'source': 'opencv_dnn_mobilenet_ssd'},
        ], allowed_labels={'cup'})

        self.assertEqual(target, {})


if __name__ == '__main__':
    unittest.main()
