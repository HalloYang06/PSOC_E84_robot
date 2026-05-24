#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import select
import socket
import struct
import threading
import time
from dataclasses import dataclass

import rclpy
from rclpy._rclpy_pybind11 import RCLError
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import String
from trajectory_msgs.msg import JointTrajectory


CAN_FRAME_FMT = '=IB3x8s'
CAN_FRAME_SIZE = struct.calcsize(CAN_FRAME_FMT)
CAN_SFF_MASK = 0x000007FF
CAN_EFF_FLAG = 0x80000000
CAN_EFF_MASK = 0x1FFFFFFF

PSOC_CMD_ID = 0x320
NANOPI_HEARTBEAT_ID = 0x321
PSOC_STATUS_ID = 0x322
F103_SENSOR_ID = 0x7C2
F103_HEALTH_ID = 0x7C3

CMD_SET_TARGET = 0x03
CMD_HEARTBEAT_SEQ_MASK = 0xFF

JOINT_NAMES = [
    'shoulder_lift_joint',
    'elbow_lift_joint',
    'shoulder_abduction_joint',
    'upper_arm_rotation_joint',
    'forearm_rotation_joint',
]

JOINT_IDS = {
    'shoulder_lift_joint': 0,
    'elbow_lift_joint': 1,
    'shoulder_abduction_joint': 2,
    'upper_arm_rotation_joint': 3,
    'forearm_rotation_joint': 4,
}

LIMITS = {
    'shoulder_lift_joint': (-0.70, 1.40),
    'elbow_lift_joint': (0.00, 1.80),
    'shoulder_abduction_joint': (-0.45, 0.80),
    'upper_arm_rotation_joint': (-1.20, 1.20),
    'forearm_rotation_joint': (-1.20, 1.20),
}


@dataclass
class CanFrame:
    can_id: int
    data: bytes
    extended: bool = False


@dataclass
class TrajectoryPointRuntime:
    due_time: float
    positions: dict[str, float]


def clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def i16_le(value: int) -> bytes:
    return struct.pack('<h', int(value))


def pack_frame(frame: CanFrame) -> bytes:
    can_id = frame.can_id & (CAN_EFF_MASK if frame.extended else CAN_SFF_MASK)
    if frame.extended:
        can_id |= CAN_EFF_FLAG
    data = frame.data[:8]
    return struct.pack(CAN_FRAME_FMT, can_id, len(data), data.ljust(8, b'\x00'))


def unpack_frame(raw: bytes) -> CanFrame:
    can_id_raw, dlc, data = struct.unpack(CAN_FRAME_FMT, raw[:CAN_FRAME_SIZE])
    extended = bool(can_id_raw & CAN_EFF_FLAG)
    can_id = can_id_raw & (CAN_EFF_MASK if extended else CAN_SFF_MASK)
    return CanFrame(can_id=can_id, data=data[:dlc], extended=extended)


def target_frame(joint_id: int, position_rad: float, rpm: int = 5, torque_ma: int = 0) -> CanFrame:
    deg_x10 = int(math.degrees(position_rad) * 10.0)
    payload = bytes([CMD_SET_TARGET, joint_id & 0xFF]) + i16_le(deg_x10) + i16_le(rpm) + i16_le(torque_ma)
    return CanFrame(PSOC_CMD_ID, payload, False)


class PsocCanBridgeNode(Node):
    def __init__(self):
        super().__init__('rehab_arm_psoc_bridge')
        self.declare_parameter('interface', 'can0')
        self.declare_parameter('send_rate_hz', 50.0)
        self.declare_parameter('default_rpm', 5)
        self.declare_parameter('log_heartbeat', False)

        self.iface = str(self.get_parameter('interface').value)
        self.send_rate_hz = float(self.get_parameter('send_rate_hz').value)
        self.default_rpm = int(self.get_parameter('default_rpm').value)
        self.log_heartbeat = bool(self.get_parameter('log_heartbeat').value)

        self.sock = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
        self.sock.bind((self.iface,))
        self.sock.setblocking(False)
        self.sock_lock = threading.Lock()
        self.running = True

        self.current_positions = {name: 0.0 for name in JOINT_NAMES}
        self.pending_points: list[TrajectoryPointRuntime] = []
        self.pending_lock = threading.Lock()
        self.heartbeat_seq = 0

        self.joint_pub = self.create_publisher(JointState, '/joint_states', 20)
        self.safety_pub = self.create_publisher(String, '/rehab_arm/safety_state', 10)
        self.sensor_pub = self.create_publisher(String, '/rehab_arm/sensor_state', 20)
        self.traj_sub = self.create_subscription(
            JointTrajectory,
            '/arm_controller/joint_trajectory',
            self.on_trajectory,
            10,
        )

        self.send_timer = self.create_timer(1.0 / self.send_rate_hz, self.on_send_timer)
        self.heartbeat_timer = self.create_timer(1.0, self.on_heartbeat_timer)
        self.rx_thread = threading.Thread(target=self.rx_loop, daemon=True)
        self.rx_thread.start()
        self.publish_safety('ok', 'bridge started')
        self.get_logger().info(f'PSoC CAN bridge ready on {self.iface}')

    def destroy_node(self):
        self.running = False
        if hasattr(self, 'rx_thread'):
            self.rx_thread.join(timeout=1.0)
        if hasattr(self, 'sock'):
            self.sock.close()
        super().destroy_node()

    def on_trajectory(self, msg: JointTrajectory) -> None:
        name_to_src = {name: i for i, name in enumerate(msg.joint_names)}
        known_names = [name for name in JOINT_NAMES if name in name_to_src]
        if not known_names:
            self.publish_safety('limited', 'trajectory has no known joints')
            return

        now = time.monotonic()
        points: list[TrajectoryPointRuntime] = []
        last_due = now
        for point in msg.points:
            positions = dict(self.current_positions)
            for name in known_names:
                src_i = name_to_src[name]
                if src_i < len(point.positions):
                    low, high = LIMITS[name]
                    positions[name] = clamp(float(point.positions[src_i]), low, high)
            offset = point.time_from_start.sec + point.time_from_start.nanosec / 1e9
            due = now + max(offset, 0.02)
            if due <= last_due:
                due = last_due + 0.02
            points.append(TrajectoryPointRuntime(due, positions))
            last_due = due

        with self.pending_lock:
            self.pending_points = points
        self.publish_safety('ok', f'accepted {len(points)} trajectory points')

    def on_send_timer(self) -> None:
        point = None
        now = time.monotonic()
        with self.pending_lock:
            if self.pending_points and now >= self.pending_points[0].due_time:
                point = self.pending_points.pop(0)

        if point is None:
            return

        self.current_positions.update(point.positions)
        for name in JOINT_NAMES:
            joint_id = JOINT_IDS[name]
            self.send_frame(target_frame(joint_id, self.current_positions[name], self.default_rpm, 0))
            time.sleep(0.002)
        self.publish_joint_state()

    def on_heartbeat_timer(self) -> None:
        self.heartbeat_seq = (self.heartbeat_seq + 1) & CMD_HEARTBEAT_SEQ_MASK
        self.send_frame(
            CanFrame(NANOPI_HEARTBEAT_ID, bytes([self.heartbeat_seq]), False),
            log=self.log_heartbeat,
        )

    def send_frame(self, frame: CanFrame, log: bool = True) -> None:
        with self.sock_lock:
            self.sock.send(pack_frame(frame))
        if log:
            self.get_logger().info(f'TX {frame.can_id:03X} {frame.data.hex().upper()}')

    def rx_loop(self) -> None:
        while self.running:
            try:
                readable, _, _ = select.select([self.sock], [], [], 0.1)
                if not readable:
                    continue
                frame = unpack_frame(self.sock.recv(CAN_FRAME_SIZE))
                self.handle_rx(frame)
            except OSError:
                return
            except Exception as exc:
                self.get_logger().warn(f'CAN RX failed: {exc}')

    def handle_rx(self, frame: CanFrame) -> None:
        if frame.can_id == PSOC_STATUS_ID:
            self.handle_psoc_status(frame)
        elif frame.can_id == F103_SENSOR_ID:
            self.handle_f103_sensor(frame)
        elif frame.can_id == F103_HEALTH_ID:
            self.handle_f103_health(frame)

    def handle_psoc_status(self, frame: CanFrame) -> None:
        payload = {
            'state': 'ok',
            'source': 'psoc',
            'id_hex': '0x322',
            'data': frame.data.hex().upper(),
        }
        if len(frame.data) >= 4:
            payload['marker'] = frame.data[0]
            payload['seq'] = frame.data[1]
            payload['motors'] = frame.data[2]
            payload['error_code'] = frame.data[3]
            if frame.data[3] != 0:
                payload['state'] = 'fault'
        self.safety_pub.publish(String(data=json.dumps(payload, separators=(',', ':'))))

    def handle_f103_sensor(self, frame: CanFrame) -> None:
        payload = {'source': 'f103', 'id_hex': '0x7C2', 'data': frame.data.hex().upper()}
        if len(frame.data) >= 8:
            payload.update({
                'emg_raw': int.from_bytes(frame.data[0:2], 'little', signed=False),
                'emg_filtered': int.from_bytes(frame.data[2:4], 'little', signed=True),
                'hr_raw': int.from_bytes(frame.data[4:6], 'little', signed=False),
                'heart_rate': frame.data[6],
                'flags': frame.data[7],
            })
        self.sensor_pub.publish(String(data=json.dumps(payload, separators=(',', ':'))))

    def handle_f103_health(self, frame: CanFrame) -> None:
        payload = {'source': 'f103_health', 'id_hex': '0x7C3', 'data': frame.data.hex().upper()}
        if len(frame.data) >= 4:
            payload.update({
                'state': frame.data[0],
                'error_count': int.from_bytes(frame.data[1:3], 'little'),
                'queue_fill': frame.data[3],
            })
        self.sensor_pub.publish(String(data=json.dumps(payload, separators=(',', ':'))))

    def publish_joint_state(self) -> None:
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.name = JOINT_NAMES
        msg.position = [self.current_positions[name] for name in JOINT_NAMES]
        msg.velocity = [0.0] * len(JOINT_NAMES)
        msg.effort = [0.0] * len(JOINT_NAMES)
        self.joint_pub.publish(msg)

    def publish_safety(self, state: str, detail: str) -> None:
        payload = {'state': state, 'detail': detail, 'source': 'psoc_bridge'}
        self.safety_pub.publish(String(data=json.dumps(payload, separators=(',', ':'))))


def main(args=None):
    rclpy.init(args=args)
    node = PsocCanBridgeNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException, RCLError):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
