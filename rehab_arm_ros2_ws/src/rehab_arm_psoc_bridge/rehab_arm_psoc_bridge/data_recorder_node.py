#!/usr/bin/env python3
from __future__ import annotations

import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String

from rehab_arm_psoc_bridge.data_recording import (
    make_jsonl_record,
    make_session_metadata,
    session_log_path,
    write_jsonl_record,
)


class RehabArmDataRecorder(Node):
    def __init__(self):
        super().__init__('rehab_arm_data_recorder')
        self.declare_parameter('output_dir', '~/rehab_arm_logs')
        self.declare_parameter('session_id', '')
        self.declare_parameter('device_id', 'nanopi')
        self.declare_parameter('robot_id', 'rehab_arm')
        self.declare_parameter('software_version', 'unknown')
        self.declare_parameter('mode', 'logging_only')
        self.declare_parameter('flush_every', 1)

        output_dir = str(self.get_parameter('output_dir').value)
        session_id = str(self.get_parameter('session_id').value)
        if not session_id:
            session_id = time.strftime('rehab_arm_%Y%m%d_%H%M%S')
        device_id = str(self.get_parameter('device_id').value)
        robot_id = str(self.get_parameter('robot_id').value)
        software_version = str(self.get_parameter('software_version').value)
        mode = str(self.get_parameter('mode').value)
        self.flush_every = max(1, int(self.get_parameter('flush_every').value))
        self.write_count = 0

        self.path = session_log_path(output_dir, session_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.log_handle = self.path.open('a', encoding='utf-8')
        write_jsonl_record(
            self.log_handle,
            make_session_metadata(
                session_id=session_id,
                device_id=device_id,
                robot_id=robot_id,
                software_version=software_version,
                mode=mode,
            ),
        )
        self.log_handle.flush()

        self.create_subscription(String, '/rehab_arm/safety_state', self.on_safety_state, 20)
        self.create_subscription(String, '/rehab_arm/sensor_state', self.on_sensor_state, 50)
        self.get_logger().info(f'recording rehab arm data to {self.path}')

    def destroy_node(self):
        if hasattr(self, 'log_handle') and not self.log_handle.closed:
            self.log_handle.flush()
            self.log_handle.close()
        super().destroy_node()

    def on_safety_state(self, msg: String) -> None:
        self.record('/rehab_arm/safety_state', msg.data)

    def on_sensor_state(self, msg: String) -> None:
        self.record('/rehab_arm/sensor_state', msg.data)

    def record(self, topic: str, text: str) -> None:
        write_jsonl_record(self.log_handle, make_jsonl_record(topic, text))
        self.write_count += 1
        if self.write_count % self.flush_every == 0:
            self.log_handle.flush()


def main(args=None):
    rclpy.init(args=args)
    node = RehabArmDataRecorder()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
