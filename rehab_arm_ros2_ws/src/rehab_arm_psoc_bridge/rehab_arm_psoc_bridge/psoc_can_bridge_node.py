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

from rehab_arm_psoc_bridge.psoc_motor_status import (
    M33MotorStatusAggregator,
    is_m33_motor_status_id,
    make_current_position_updates_from_m33_motor_state,
    make_joint_state_fields_from_m33_motor_state,
)
from rehab_arm_psoc_bridge.safety_gate import psoc_motion_gate_detail
from rehab_arm_psoc_bridge.psoc_status import parse_psoc_status_payload
from rehab_arm_psoc_bridge.safety_state import bridge_safety_payload


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
    joint_names: list[str]


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
        self.declare_parameter('status_timeout_sec', 2.5)
        self.declare_parameter('require_psoc_ok_for_trajectory', True)
        self.declare_parameter('reject_out_of_limit_trajectory', True)
        self.declare_parameter('max_trajectory_points', 100)
        self.declare_parameter('enable_target_tx', False)
        self.declare_parameter('robot_id', 'rehab-arm-alpha')
        self.declare_parameter('device_id', 'nanopi-m5')

        self.iface = str(self.get_parameter('interface').value)
        self.send_rate_hz = float(self.get_parameter('send_rate_hz').value)
        self.default_rpm = int(self.get_parameter('default_rpm').value)
        self.log_heartbeat = bool(self.get_parameter('log_heartbeat').value)
        self.status_timeout_sec = float(self.get_parameter('status_timeout_sec').value)
        self.require_psoc_ok_for_trajectory = bool(
            self.get_parameter('require_psoc_ok_for_trajectory').value
        )
        self.reject_out_of_limit_trajectory = bool(
            self.get_parameter('reject_out_of_limit_trajectory').value
        )
        self.max_trajectory_points = int(self.get_parameter('max_trajectory_points').value)
        self.enable_target_tx = bool(self.get_parameter('enable_target_tx').value)
        self.robot_id = str(self.get_parameter('robot_id').value)
        self.device_id = str(self.get_parameter('device_id').value)

        self.sock = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
        self.sock.bind((self.iface,))
        self.sock.setblocking(False)
        self.sock_lock = threading.Lock()
        self.running = True

        self.current_positions = {name: 0.0 for name in JOINT_NAMES}
        self.pending_points: list[TrajectoryPointRuntime] = []
        self.pending_lock = threading.Lock()
        self.heartbeat_seq = 0
        self.heartbeat_tx_count = 0
        self.status_rx_count = 0
        self.last_status_time: float | None = None
        self.last_psoc_status_payload: dict[str, object] | None = None
        self.last_psoc_motion_allowed = False
        self.last_psoc_error_code: int | None = None
        self.last_safety_state = ''
        self.target_tx_count = 0
        self.target_dry_run_count = 0
        self.motor_status_rx_count = 0
        self.motor_status_aggregator = M33MotorStatusAggregator(self.robot_id, self.device_id)

        self.joint_pub = self.create_publisher(JointState, '/joint_states', 20)
        self.safety_pub = self.create_publisher(String, '/rehab_arm/safety_state', 10)
        self.sensor_pub = self.create_publisher(String, '/rehab_arm/sensor_state', 20)
        self.motor_pub = self.create_publisher(String, '/rehab_arm/motor_state', 20)
        self.traj_sub = self.create_subscription(
            JointTrajectory,
            '/arm_controller/joint_trajectory',
            self.on_trajectory,
            10,
        )

        self.send_timer = self.create_timer(1.0 / self.send_rate_hz, self.on_send_timer)
        self.heartbeat_timer = self.create_timer(1.0, self.on_heartbeat_timer)
        self.diagnostic_timer = self.create_timer(1.0, self.on_diagnostic_timer)
        self.rx_thread = threading.Thread(target=self.rx_loop, daemon=True)
        self.rx_thread.start()
        self.publish_safety('limited', 'bridge started, waiting for PSoC status')
        self.get_logger().info(
            f'PSoC CAN bridge ready on {self.iface}; enable_target_tx={self.enable_target_tx}'
        )

    def destroy_node(self):
        self.running = False
        if hasattr(self, 'rx_thread'):
            self.rx_thread.join(timeout=1.0)
        if hasattr(self, 'sock'):
            self.sock.close()
        super().destroy_node()

    def on_trajectory(self, msg: JointTrajectory) -> None:
        gate_ok, gate_detail = self.trajectory_gate_state()
        if not gate_ok:
            with self.pending_lock:
                self.pending_points = []
            self.publish_safety('limited', f'rejected trajectory: {gate_detail}')
            return

        name_to_src = {name: i for i, name in enumerate(msg.joint_names)}
        known_names = [name for name in JOINT_NAMES if name in name_to_src]
        if not known_names:
            self.publish_safety('limited', 'trajectory has no known joints')
            return
        if not msg.points:
            self.publish_safety('limited', 'trajectory has no points')
            return
        if len(msg.points) > self.max_trajectory_points:
            self.publish_safety(
                'limited',
                f'trajectory has {len(msg.points)} points, max is {self.max_trajectory_points}',
            )
            return

        now = time.monotonic()
        points: list[TrajectoryPointRuntime] = []
        last_due = now
        for point_i, point in enumerate(msg.points):
            positions = dict(self.current_positions)
            for name in known_names:
                src_i = name_to_src[name]
                if src_i < len(point.positions):
                    raw_position = float(point.positions[src_i])
                    if not math.isfinite(raw_position):
                        self.publish_safety(
                            'limited',
                            f'trajectory point {point_i} joint {name} is not finite',
                        )
                        return
                    low, high = LIMITS[name]
                    if raw_position < low or raw_position > high:
                        if self.reject_out_of_limit_trajectory:
                            self.publish_safety(
                                'limited',
                                (
                                    f'trajectory point {point_i} joint {name} '
                                    f'{raw_position:.3f} outside [{low:.3f}, {high:.3f}]'
                                ),
                            )
                            return
                        raw_position = clamp(raw_position, low, high)
                    positions[name] = raw_position
            offset = point.time_from_start.sec + point.time_from_start.nanosec / 1e9
            due = now + max(offset, 0.02)
            if due <= last_due:
                due = last_due + 0.02
            points.append(TrajectoryPointRuntime(due, positions, list(known_names)))
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

        gate_ok, gate_detail = self.trajectory_gate_state()
        if not gate_ok:
            with self.pending_lock:
                self.pending_points = []
            self.publish_safety('limited', f'stopped trajectory send: {gate_detail}')
            return

        sent_any = False
        for name in point.joint_names:
            joint_id = JOINT_IDS[name]
            frame = target_frame(joint_id, point.positions[name], self.default_rpm, 0)
            sent_any = self.emit_target_frame(name, frame) or sent_any
            time.sleep(0.002)
        if sent_any:
            self.current_positions.update(point.positions)
            self.publish_joint_state()

    def on_heartbeat_timer(self) -> None:
        self.heartbeat_seq = (self.heartbeat_seq + 1) & CMD_HEARTBEAT_SEQ_MASK
        self.heartbeat_tx_count += 1
        self.send_frame(
            CanFrame(NANOPI_HEARTBEAT_ID, bytes([self.heartbeat_seq]), False),
            log=self.log_heartbeat,
        )

    def on_diagnostic_timer(self) -> None:
        if self.last_status_time is not None:
            age = time.monotonic() - self.last_status_time
            if age <= self.status_timeout_sec:
                return
            detail = f'no PSoC status for {age:.1f}s after {self.status_rx_count} status frames'
            self.last_psoc_motion_allowed = False
        elif self.heartbeat_tx_count > 0:
            detail = f'no PSoC status after {self.heartbeat_tx_count} heartbeats'
        else:
            return
        self.publish_safety('limited', detail)

    def trajectory_gate_state(self) -> tuple[bool, str]:
        if not self.require_psoc_ok_for_trajectory:
            return True, 'PSoC ok gate disabled'
        if self.last_status_time is None:
            return False, 'no PSoC status received'
        age = time.monotonic() - self.last_status_time
        if age > self.status_timeout_sec:
            return False, f'PSoC status stale for {age:.1f}s'
        return psoc_motion_gate_detail(self.last_psoc_status_payload)

    def send_frame(self, frame: CanFrame, log: bool = True) -> None:
        with self.sock_lock:
            self.sock.send(pack_frame(frame))
        if log:
            self.get_logger().info(f'TX {frame.can_id:03X} {frame.data.hex().upper()}')

    def emit_target_frame(self, joint_name: str, frame: CanFrame) -> bool:
        if not self.enable_target_tx:
            self.target_dry_run_count += 1
            self.get_logger().info(
                f'DRY-RUN {frame.can_id:03X} joint={joint_name} data={frame.data.hex().upper()}'
            )
            return False
        self.target_tx_count += 1
        self.send_frame(frame)
        return True

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
        elif is_m33_motor_status_id(frame.can_id):
            self.handle_m33_motor_status(frame)
        elif frame.can_id == F103_SENSOR_ID:
            self.handle_f103_sensor(frame)
        elif frame.can_id == F103_HEALTH_ID:
            self.handle_f103_health(frame)

    def handle_psoc_status(self, frame: CanFrame) -> None:
        self.last_status_time = time.monotonic()
        self.status_rx_count += 1
        payload = parse_psoc_status_payload(frame.data)
        error_code = payload.get('error_code')
        self.last_psoc_error_code = error_code if isinstance(error_code, int) else None
        self.last_psoc_status_payload = payload
        self.last_psoc_motion_allowed = payload.get('motion_allowed') is True
        self.safety_pub.publish(String(data=json.dumps(payload, separators=(',', ':'))))

    def handle_m33_motor_status(self, frame: CanFrame) -> None:
        payload = self.motor_status_aggregator.accept_frame(frame.can_id, frame.data)
        if payload is None:
            self.get_logger().warn(
                f'ignored invalid M33 motor status {frame.can_id:03X} {frame.data.hex().upper()}'
            )
            return
        self.motor_status_rx_count += 1
        self.motor_pub.publish(String(data=json.dumps(payload, separators=(',', ':'))))
        self.current_positions.update(
            make_current_position_updates_from_m33_motor_state(payload, JOINT_NAMES)
        )
        self.publish_joint_state_from_motor_payload(payload)

    def publish_joint_state_from_motor_payload(self, payload: dict[str, object]) -> None:
        fields = make_joint_state_fields_from_m33_motor_state(payload)
        if not fields['name']:
            return
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.name = fields['name']
        msg.position = fields['position']
        msg.velocity = fields['velocity']
        msg.effort = fields['effort']
        self.joint_pub.publish(msg)

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
        state_key = f'{state}:{detail}'
        if state_key == self.last_safety_state:
            return
        self.last_safety_state = state_key
        if state == 'ok':
            self.get_logger().info(f'safety ok: {detail}')
        else:
            self.get_logger().warn(f'safety {state}: {detail}')
        payload = bridge_safety_payload(state, detail)
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
