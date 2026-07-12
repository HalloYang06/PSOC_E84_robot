#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

try:
    import rclpy
    from rclpy.executors import ExternalShutdownException
    from rclpy.node import Node
    from std_msgs.msg import String
except ModuleNotFoundError:
    rclpy = None
    ExternalShutdownException = Exception
    Node = object
    String = None

from rehab_arm_psoc_bridge.data_recording import (
    file_sha256,
    make_camera_keyframe_payload,
    make_default_session_id,
    sanitize_identifier,
)


def build_ffmpeg_capture_command(
    device: str,
    output_path: str,
    width: int,
    height: int,
    quality: int,
    input_format: str = '',
) -> list[str]:
    command = [
        'ffmpeg',
        '-hide_banner',
        '-loglevel',
        'error',
        '-y',
        '-f',
        'v4l2',
    ]
    if input_format:
        command.extend(['-input_format', input_format])
    command.extend([
        '-video_size',
        f'{width}x{height}',
        '-i',
        device,
        '-frames:v',
        '1',
        '-q:v',
        str(quality),
        output_path,
    ])
    return command


class CameraKeyframeNode(Node):
    def __init__(self):
        super().__init__('rehab_arm_camera_keyframe')
        self.declare_parameter('device', '/dev/video0')
        self.declare_parameter('output_dir', '~/rehab_arm_frames')
        self.declare_parameter('camera_id', 'front_rgb')
        self.declare_parameter('robot_id', 'rehab-arm-alpha')
        self.declare_parameter('device_id', 'nanopi-m5')
        self.declare_parameter('width', 640)
        self.declare_parameter('height', 480)
        self.declare_parameter('quality', 5)
        self.declare_parameter('interval_sec', 5.0)
        self.declare_parameter('input_format', '')
        self.declare_parameter('publish_once', False)

        self.video_device = str(self.get_parameter('device').value)
        self.output_dir = Path(str(self.get_parameter('output_dir').value)).expanduser()
        self.camera_id = str(self.get_parameter('camera_id').value)
        self.robot_id = str(self.get_parameter('robot_id').value)
        self.device_id = str(self.get_parameter('device_id').value)
        self.width = int(self.get_parameter('width').value)
        self.height = int(self.get_parameter('height').value)
        self.quality = int(self.get_parameter('quality').value)
        self.interval_sec = float(self.get_parameter('interval_sec').value)
        self.input_format = str(self.get_parameter('input_format').value)
        self.publish_once = bool(self.get_parameter('publish_once').value)

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.publisher = self.create_publisher(String, '/rehab_arm/camera_keyframe', 10)
        self.sequence = 0
        self.timer = self.create_timer(max(0.1, self.interval_sec), self.capture_and_publish)
        self.get_logger().info(
            f'camera keyframe capture device={self.video_device} size={self.width}x{self.height} '
            f'output_dir={self.output_dir}'
        )
        if self.publish_once:
            self.capture_and_publish()

    def next_frame_path(self) -> Path:
        self.sequence += 1
        timestamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
        session_prefix = sanitize_identifier(make_default_session_id(self.robot_id, self.device_id))
        return self.output_dir / f'{session_prefix}__{self.camera_id}__{timestamp}__{self.sequence:04d}.jpg'

    def capture_frame(self, output_path: Path) -> None:
        command = build_ffmpeg_capture_command(
            device=self.video_device,
            output_path=str(output_path),
            width=self.width,
            height=self.height,
            quality=self.quality,
            input_format=self.input_format,
        )
        result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or f'ffmpeg exited {result.returncode}').strip())
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError(f'capture produced empty file: {output_path}')

    def capture_and_publish(self) -> None:
        output_path = self.next_frame_path()
        try:
            self.capture_frame(output_path)
            payload = make_camera_keyframe_payload(
                camera_id=self.camera_id,
                image_path=str(output_path),
                sha256=file_sha256(output_path),
                robot_id=self.robot_id,
                device_id=self.device_id,
                width=self.width,
                height=self.height,
                image_format='jpg',
            )
            msg = String()
            msg.data = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
            self.publisher.publish(msg)
            self.get_logger().info(f'published camera keyframe {output_path}')
        except Exception as exc:
            self.get_logger().warning(f'camera keyframe capture failed: {exc}')
        if self.publish_once:
            rclpy.shutdown()


def main(args=None):
    if rclpy is None:
        raise RuntimeError('camera_keyframe_node.py requires ROS2 rclpy')
    rclpy.init(args=args)
    node = CameraKeyframeNode()
    try:
        if rclpy.ok():
            rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
