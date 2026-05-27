#!/usr/bin/env python3
"""NanoPi SocketCAN master for motor, M33 bridge, and F103 link tests."""

from __future__ import annotations

import argparse
import math
import os
import select
import socket
import struct
import subprocess
import sys
import time
from dataclasses import dataclass


CAN_EFF_FLAG = 0x80000000
CAN_RTR_FLAG = 0x40000000
CAN_ERR_FLAG = 0x20000000
CAN_EFF_MASK = 0x1FFFFFFF
CAN_SFF_MASK = 0x000007FF
CAN_FRAME_FMT = "=IB3x8s"
CAN_FRAME_SIZE = struct.calcsize(CAN_FRAME_FMT)

DEFAULT_IFACE = os.environ.get("CAN_INTERFACE", "can0")
DEFAULT_BITRATE = int(os.environ.get("CAN_BITRATE", "1000000"))

MASTER_ID = 0xFD

MOTOR_TYPE_GET_ID = 0x00
MOTOR_TYPE_CTRL = 0x01
MOTOR_TYPE_FEEDBACK = 0x02
MOTOR_TYPE_ENABLE = 0x03
MOTOR_TYPE_STOP = 0x04
MOTOR_TYPE_SET_ZERO = 0x06
MOTOR_TYPE_PARAM_READ = 0x11
MOTOR_TYPE_PARAM_WRITE = 0x12
MOTOR_TYPE_ACTIVE_REPORT = 0x18

PARAM_RUN_MODE = 0x7005
PARAM_SPD_REF = 0x700A
PARAM_LOC_REF = 0x7016
PARAM_LIMIT_SPD = 0x7017
PARAM_LIMIT_CUR = 0x7018
PARAM_SPEED_ACC = 0x7022

RUN_MODE_MIT = 0
RUN_MODE_PP = 1
RUN_MODE_SPEED = 2
RUN_MODE_CURRENT = 3
RUN_MODE_CSP = 5

MOTOR_P_MIN = -12.57
MOTOR_P_MAX = 12.57
MOTOR_V_MIN = -33.0
MOTOR_V_MAX = 33.0
MOTOR_KP_MIN = 0.0
MOTOR_KP_MAX = 500.0
MOTOR_KD_MIN = 0.0
MOTOR_KD_MAX = 5.0
MOTOR_T_MIN = -14.0
MOTOR_T_MAX = 14.0

CANSIMPLE_CMD_HEARTBEAT = 0x01
CANSIMPLE_CMD_GET_ERROR = 0x03
CANSIMPLE_CMD_ADDRESS = 0x06
CANSIMPLE_CMD_SET_AXIS_STATE = 0x07
CANSIMPLE_CMD_MIT_CONTROL = 0x08
CANSIMPLE_CMD_SET_CONTROLLER_MODE = 0x0B
CANSIMPLE_CMD_SET_INPUT_POS = 0x0C
CANSIMPLE_CMD_SET_INPUT_VEL = 0x0D
CANSIMPLE_CMD_SET_INPUT_TORQUE = 0x0E
CANSIMPLE_CMD_SET_LIMITS = 0x0F
CANSIMPLE_CMD_CLEAR_ERRORS = 0x18

CANSIMPLE_AXIS_IDLE = 1
CANSIMPLE_AXIS_CLOSED_LOOP = 8
CANSIMPLE_CONTROL_TORQUE = 1
CANSIMPLE_CONTROL_VELOCITY = 2
CANSIMPLE_CONTROL_POSITION = 3
CANSIMPLE_INPUT_PASSTHROUGH = 1
CANSIMPLE_NODE_BROADCAST = 0x3F

ROS_CMD_ID = 0x320
NANOPI_HEARTBEAT_ID = 0x321
M33_STATUS_ID = 0x322

ROS_CMD_ENABLE = 0x01
ROS_CMD_STOP = 0x02
ROS_CMD_SET_TARGET = 0x03
ROS_CMD_SET_MODE = 0x04
ROS_CMD_SET_ZERO = 0x05
ROS_CMD_ACTIVE_REPORT = 0x06

F103_CTRL_ID = 0x7C0
F103_ACK_ID = 0x7C1
F103_SENSOR_ID = 0x7C2
F103_HEALTH_ID = 0x7C3
F103_CMD_SET_RATE = 0x01
F103_CMD_START_STREAM = 0x03
F103_CMD_STOP_STREAM = 0x04
F103_CMD_GET_STATUS = 0x05
F103_RATE_TARGET_CAN_TX = 0x02


@dataclass
class CanFrame:
    can_id: int
    data: bytes
    extended: bool = False
    is_rx: bool = True
    timestamp: float = 0.0

    def cansend_text(self) -> str:
        marker = "##" if False else "#"
        suffix = "x" if self.extended else ""
        return f"{self.can_id:08X}{suffix}{marker}{self.data.hex().upper()}"


def parse_int(value: str) -> int:
    return int(value, 0)


def parse_hex_bytes(value: str) -> bytes:
    text = value.replace(" ", "").replace(":", "").replace("-", "")
    if len(text) % 2:
        text = "0" + text
    return bytes.fromhex(text) if text else b""


def clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def float_to_uint(value: float, low: float, high: float, bits: int) -> int:
    value = clamp(value, low, high)
    return int(((value - low) * ((1 << bits) - 1) / (high - low)) + 0.5)


def uint_to_float(value: int, low: float, high: float, bits: int) -> float:
    return float(value) * (high - low) / float((1 << bits) - 1) + low


def i16_le(value: int) -> bytes:
    return struct.pack("<h", int(value))


def u16_le(value: int) -> bytes:
    return struct.pack("<H", int(value) & 0xFFFF)


def u32_le(value: int) -> bytes:
    return struct.pack("<I", int(value) & 0xFFFFFFFF)


def f32_le(value: float) -> bytes:
    return struct.pack("<f", float(value))


def private_ext_id(comm_type: int, data2: int, data1: int) -> int:
    return ((comm_type & 0x1F) << 24) | ((data2 & 0xFFFF) << 8) | (data1 & 0xFF)


def cansimple_id(node_id: int, cmd_id: int) -> int:
    return ((node_id & 0x3F) << 5) | (cmd_id & 0x1F)


def pack_frame(frame: CanFrame) -> bytes:
    can_id = frame.can_id & (CAN_EFF_MASK if frame.extended else CAN_SFF_MASK)
    if frame.extended:
        can_id |= CAN_EFF_FLAG
    data = frame.data[:8]
    return struct.pack(CAN_FRAME_FMT, can_id, len(data), data.ljust(8, b"\x00"))


def unpack_frame(raw: bytes) -> CanFrame:
    can_id_raw, dlc, data = struct.unpack(CAN_FRAME_FMT, raw[:CAN_FRAME_SIZE])
    extended = bool(can_id_raw & CAN_EFF_FLAG)
    can_id = can_id_raw & (CAN_EFF_MASK if extended else CAN_SFF_MASK)
    return CanFrame(can_id=can_id, data=data[:dlc], extended=extended, timestamp=time.time())


def open_can(iface: str) -> socket.socket:
    sock = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    sock.bind((iface,))
    return sock


def send(sock: socket.socket, frame: CanFrame) -> None:
    sock.send(pack_frame(frame))
    print(format_frame("TX", frame))


def recv_until(sock: socket.socket, timeout: float, ids: set[int] | None = None) -> list[CanFrame]:
    end = time.monotonic() + timeout
    frames: list[CanFrame] = []
    while time.monotonic() < end:
        readable, _, _ = select.select([sock], [], [], max(0.0, min(0.1, end - time.monotonic())))
        if not readable:
            continue
        frame = unpack_frame(sock.recv(CAN_FRAME_SIZE))
        if ids is None or frame.can_id in ids:
            frames.append(frame)
            print(format_frame("RX", frame))
    return frames


def format_frame(prefix: str, frame: CanFrame) -> str:
    kind = "EXT" if frame.extended else "STD"
    data = " ".join(f"{b:02X}" for b in frame.data)
    return f"{prefix} {kind} 0x{frame.can_id:08X} [{len(frame.data)}] {data}"


def describe_frame(frame: CanFrame) -> str:
    if frame.extended:
        comm_type = (frame.can_id >> 24) & 0x1F
        data2 = (frame.can_id >> 8) & 0xFFFF
        data1 = frame.can_id & 0xFF
        details = f" private(type=0x{comm_type:02X}, data2=0x{data2:04X}, data1=0x{data1:02X})"
        if comm_type in (MOTOR_TYPE_FEEDBACK, MOTOR_TYPE_ACTIVE_REPORT) and len(frame.data) >= 8:
            pos = uint_to_float((frame.data[0] << 8) | frame.data[1], MOTOR_P_MIN, MOTOR_P_MAX, 16)
            vel = uint_to_float((frame.data[2] << 8) | frame.data[3], MOTOR_V_MIN, MOTOR_V_MAX, 16)
            torque = uint_to_float((frame.data[4] << 8) | frame.data[5], MOTOR_T_MIN, MOTOR_T_MAX, 16)
            temp = frame.data[6]
            details += f" fb(pos={pos:.3f}rad vel={vel:.3f}rad/s torque={torque:.3f}Nm temp={temp}C)"
        return details

    node_id = (frame.can_id >> 5) & 0x3F
    cmd_id = frame.can_id & 0x1F
    if frame.can_id == M33_STATUS_ID and len(frame.data) >= 8:
        tick = int.from_bytes(frame.data[4:8], "little")
        return f" m33_status(marker=0x{frame.data[0]:02X}, seq={frame.data[1]}, motors={frame.data[2]}, tick={tick})"
    if frame.can_id == F103_ACK_ID and len(frame.data) >= 3:
        return f" f103_ack(cmd=0x{frame.data[0]:02X}, seq={frame.data[1]}, status={frame.data[2]})"
    if frame.can_id == F103_SENSOR_ID and len(frame.data) >= 8:
        emg_raw, emg_filt, hr_raw = struct.unpack("<HhH", frame.data[:6])
        return f" f103_sensor(emg_raw={emg_raw}, emg_filt={emg_filt}, hr_raw={hr_raw}, hr={frame.data[6]}, flags=0x{frame.data[7]:02X})"
    if frame.can_id == F103_HEALTH_ID and len(frame.data) >= 4:
        err = int.from_bytes(frame.data[1:3], "little")
        return f" f103_health(state={frame.data[0]}, err={err}, q={frame.data[3]})"
    if cmd_id == CANSIMPLE_CMD_HEARTBEAT and len(frame.data) >= 5:
        err = int.from_bytes(frame.data[:4], "little")
        return f" cansimple_heartbeat(node={node_id}, error=0x{err:08X}, state={frame.data[4]})"
    return ""


def ensure_can(iface: str, bitrate: int) -> None:
    subprocess.run(["sudo", "ip", "link", "set", iface, "down"], check=False)
    subprocess.run(
        ["sudo", "ip", "link", "set", iface, "type", "can", "bitrate", str(bitrate), "restart-ms", "100", "berr-reporting", "on"],
        check=True,
    )
    subprocess.run(["sudo", "ip", "link", "set", iface, "up"], check=True)
    subprocess.run(["ip", "-details", "-statistics", "link", "show", iface], check=False)


def private_control_payload(pos: float, vel: float, kp: float, kd: float) -> bytes:
    pos_u = float_to_uint(pos, MOTOR_P_MIN, MOTOR_P_MAX, 16)
    vel_u = float_to_uint(vel, MOTOR_V_MIN, MOTOR_V_MAX, 16)
    kp_u = float_to_uint(kp, MOTOR_KP_MIN, MOTOR_KP_MAX, 16)
    kd_u = float_to_uint(kd, MOTOR_KD_MIN, MOTOR_KD_MAX, 16)
    return struct.pack(">HHHH", pos_u, vel_u, kp_u, kd_u)


def frame_private_probe(motor_id: int) -> CanFrame:
    return CanFrame(private_ext_id(MOTOR_TYPE_GET_ID, MASTER_ID, motor_id), b"\x00" * 8, True)


def frame_private_enable(motor_id: int) -> CanFrame:
    return CanFrame(private_ext_id(MOTOR_TYPE_ENABLE, MASTER_ID, motor_id), b"\x00" * 8, True)


def frame_private_stop(motor_id: int, clear_fault: bool) -> CanFrame:
    return CanFrame(private_ext_id(MOTOR_TYPE_STOP, MASTER_ID, motor_id), bytes([1 if clear_fault else 0]) + b"\x00" * 7, True)


def frame_private_zero(motor_id: int) -> CanFrame:
    return CanFrame(private_ext_id(MOTOR_TYPE_SET_ZERO, MASTER_ID, motor_id), b"\x01" + b"\x00" * 7, True)


def frame_private_mode(motor_id: int, mode: int) -> CanFrame:
    payload = u16_le(PARAM_RUN_MODE) + b"\x00\x00" + bytes([mode]) + b"\x00\x00\x00"
    return CanFrame(private_ext_id(MOTOR_TYPE_PARAM_WRITE, MASTER_ID, motor_id), payload, True)


def frame_private_mit(motor_id: int, pos: float, vel: float, kp: float, kd: float, torque: float) -> CanFrame:
    torque_u = float_to_uint(torque, MOTOR_T_MIN, MOTOR_T_MAX, 16)
    return CanFrame(private_ext_id(MOTOR_TYPE_CTRL, torque_u, motor_id), private_control_payload(pos, vel, kp, kd), True)


def frame_private_write_float(motor_id: int, index: int, value: float) -> CanFrame:
    payload = u16_le(index) + b"\x00\x00" + f32_le(value)
    return CanFrame(private_ext_id(MOTOR_TYPE_PARAM_WRITE, MASTER_ID, motor_id), payload, True)


def frame_private_read(motor_id: int, index: int) -> CanFrame:
    payload = u16_le(index) + b"\x00" * 6
    return CanFrame(private_ext_id(MOTOR_TYPE_PARAM_READ, MASTER_ID, motor_id), payload, True)


def frame_private_active_report(motor_id: int, enabled: bool) -> CanFrame:
    payload = bytes([1, 2, 3, 4, 5, 6, 1 if enabled else 0, 0])
    return CanFrame(private_ext_id(MOTOR_TYPE_ACTIVE_REPORT, MASTER_ID, motor_id), payload, True)


def frame_cansimple(node_id: int, cmd_id: int, payload: bytes = b"") -> CanFrame:
    return CanFrame(cansimple_id(node_id, cmd_id), payload, False)


def frame_ros_command(op: int, joint: int, payload: bytes = b"") -> CanFrame:
    return CanFrame(ROS_CMD_ID, (bytes([op, joint]) + payload)[:8], False)


def with_socket(args: argparse.Namespace) -> socket.socket:
    return open_can(args.iface)


def cmd_setup(args: argparse.Namespace) -> int:
    ensure_can(args.iface, args.bitrate)
    return 0


def cmd_monitor(args: argparse.Namespace) -> int:
    sock = with_socket(args)
    end = None if args.seconds <= 0 else time.monotonic() + args.seconds
    try:
        while end is None or time.monotonic() < end:
            timeout = 0.2 if end is None else max(0.0, min(0.2, end - time.monotonic()))
            readable, _, _ = select.select([sock], [], [], timeout)
            if not readable:
                continue
            frame = unpack_frame(sock.recv(CAN_FRAME_SIZE))
            print(format_frame("RX", frame) + describe_frame(frame))
    finally:
        sock.close()
    return 0


def cmd_heartbeat(args: argparse.Namespace) -> int:
    sock = with_socket(args)
    try:
        send(sock, CanFrame(NANOPI_HEARTBEAT_ID, bytes([args.seq & 0xFF]), False))
        recv_until(sock, args.wait, {M33_STATUS_ID})
    finally:
        sock.close()
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    sock = with_socket(args)
    try:
        ids = [args.motor] if args.motor is not None else range(args.start, args.end + 1)
        for motor_id in ids:
            send(sock, frame_private_probe(motor_id))
            recv_until(sock, args.wait, None)
    finally:
        sock.close()
    return 0


def cmd_private(args: argparse.Namespace) -> int:
    sock = with_socket(args)
    try:
        if args.action == "enable":
            send(sock, frame_private_enable(args.motor))
        elif args.action == "stop":
            send(sock, frame_private_stop(args.motor, args.clear_fault))
        elif args.action == "zero":
            send(sock, frame_private_zero(args.motor))
        elif args.action == "mode":
            send(sock, frame_private_mode(args.motor, args.mode))
        elif args.action == "mit":
            send(sock, frame_private_mit(args.motor, args.pos, args.vel, args.kp, args.kd, args.torque))
        elif args.action == "speed":
            send(sock, frame_private_enable(args.motor))
            time.sleep(0.01)
            send(sock, frame_private_mit(args.motor, 0.0, args.vel, 0.0, args.kd, 0.0))
        elif args.action == "write-float":
            send(sock, frame_private_write_float(args.motor, args.index, args.value))
        elif args.action == "read":
            send(sock, frame_private_read(args.motor, args.index))
        elif args.action == "active-report":
            send(sock, frame_private_active_report(args.motor, args.enable_report))
        recv_until(sock, args.wait, None)
    finally:
        sock.close()
    return 0


def cmd_cansimple(args: argparse.Namespace) -> int:
    sock = with_socket(args)
    try:
        if args.action == "get-error":
            send(sock, frame_cansimple(args.node, CANSIMPLE_CMD_GET_ERROR, bytes([args.error_type & 0xFF])))
        elif args.action == "address":
            send(sock, frame_cansimple(CANSIMPLE_NODE_BROADCAST, CANSIMPLE_CMD_ADDRESS))
        elif args.action == "closed-loop":
            send(sock, frame_cansimple(args.node, CANSIMPLE_CMD_SET_AXIS_STATE, u32_le(CANSIMPLE_AXIS_CLOSED_LOOP)))
        elif args.action == "idle":
            send(sock, frame_cansimple(args.node, CANSIMPLE_CMD_SET_AXIS_STATE, u32_le(CANSIMPLE_AXIS_IDLE)))
        elif args.action == "clear":
            send(sock, frame_cansimple(args.node, CANSIMPLE_CMD_CLEAR_ERRORS, b"\x00" * 8))
        elif args.action == "vel":
            send(sock, frame_cansimple(args.node, CANSIMPLE_CMD_SET_CONTROLLER_MODE, u32_le(CANSIMPLE_CONTROL_VELOCITY) + u32_le(CANSIMPLE_INPUT_PASSTHROUGH)))
            time.sleep(0.01)
            send(sock, frame_cansimple(args.node, CANSIMPLE_CMD_SET_INPUT_VEL, f32_le(args.vel / (2.0 * math.pi)) + f32_le(args.torque)))
        elif args.action == "pos":
            send(sock, frame_cansimple(args.node, CANSIMPLE_CMD_SET_CONTROLLER_MODE, u32_le(CANSIMPLE_CONTROL_POSITION) + u32_le(CANSIMPLE_INPUT_PASSTHROUGH)))
            time.sleep(0.01)
            send(sock, frame_cansimple(args.node, CANSIMPLE_CMD_SET_INPUT_POS, f32_le(args.pos / (2.0 * math.pi)) + i16_le(0) + i16_le(0)))
        elif args.action == "torque":
            send(sock, frame_cansimple(args.node, CANSIMPLE_CMD_SET_CONTROLLER_MODE, u32_le(CANSIMPLE_CONTROL_TORQUE) + u32_le(CANSIMPLE_INPUT_PASSTHROUGH)))
            time.sleep(0.01)
            send(sock, frame_cansimple(args.node, CANSIMPLE_CMD_SET_INPUT_TORQUE, f32_le(args.torque)))
        recv_until(sock, args.wait, None)
    finally:
        sock.close()
    return 0


def cmd_m33(args: argparse.Namespace) -> int:
    sock = with_socket(args)
    try:
        if args.action == "enable":
            frame = frame_ros_command(ROS_CMD_ENABLE, args.joint)
        elif args.action == "stop":
            frame = frame_ros_command(ROS_CMD_STOP, args.joint, bytes([1 if args.clear_fault else 0]))
        elif args.action == "zero":
            frame = frame_ros_command(ROS_CMD_SET_ZERO, args.joint)
        elif args.action == "mode":
            frame = frame_ros_command(ROS_CMD_SET_MODE, args.joint, bytes([args.mode]))
        elif args.action == "active-report":
            frame = frame_ros_command(ROS_CMD_ACTIVE_REPORT, args.joint, bytes([1 if args.enable_report else 0]))
        elif args.action == "target":
            pos_01deg = int(args.deg * 10.0)
            payload = i16_le(pos_01deg) + i16_le(args.rpm) + i16_le(args.torque_ma)
            frame = frame_ros_command(ROS_CMD_SET_TARGET, args.joint, payload)
        else:
            raise ValueError(args.action)
        send(sock, frame)
        recv_until(sock, args.wait, None)
    finally:
        sock.close()
    return 0


def cmd_f103(args: argparse.Namespace) -> int:
    sock = with_socket(args)
    try:
        if args.action == "status":
            payload = bytes([F103_CMD_GET_STATUS, args.seq & 0xFF]) + b"\x00" * 6
        elif args.action == "set-rate":
            payload = bytes([F103_CMD_SET_RATE, args.seq & 0xFF, F103_RATE_TARGET_CAN_TX]) + u16_le(args.period_ms) + b"\x00" * 3
        elif args.action == "start":
            payload = bytes([F103_CMD_START_STREAM, args.seq & 0xFF]) + b"\x00" * 6
        elif args.action == "stop":
            payload = bytes([F103_CMD_STOP_STREAM, args.seq & 0xFF]) + b"\x00" * 6
        else:
            raise ValueError(args.action)
        send(sock, CanFrame(F103_CTRL_ID, payload, False))
        recv_until(sock, args.wait, {F103_ACK_ID, F103_SENSOR_ID, F103_HEALTH_ID})
    finally:
        sock.close()
    return 0


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--iface", default=DEFAULT_IFACE)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    setup = sub.add_parser("setup", help="bring up SPI-CAN interface")
    add_common(setup)
    setup.add_argument("--bitrate", type=int, default=DEFAULT_BITRATE)
    setup.set_defaults(func=cmd_setup)

    monitor = sub.add_parser("monitor", help="print decoded CAN traffic; seconds<=0 means forever")
    add_common(monitor)
    monitor.add_argument("--seconds", type=float, default=10.0)
    monitor.set_defaults(func=cmd_monitor)

    heartbeat = sub.add_parser("heartbeat", help="send NanoPi heartbeat to M33 and wait for 0x322")
    add_common(heartbeat)
    heartbeat.add_argument("--seq", type=parse_int, default=1)
    heartbeat.add_argument("--wait", type=float, default=1.0)
    heartbeat.set_defaults(func=cmd_heartbeat)

    probe = sub.add_parser("probe", help="send harmless private Get_ID probe frames")
    add_common(probe)
    probe.add_argument("--motor", type=parse_int)
    probe.add_argument("--start", type=parse_int, default=1)
    probe.add_argument("--end", type=parse_int, default=7)
    probe.add_argument("--wait", type=float, default=0.2)
    probe.set_defaults(func=cmd_probe)

    private = sub.add_parser("private", help="direct private extended-frame motor control")
    add_common(private)
    private.add_argument("action", choices=["enable", "stop", "zero", "mode", "mit", "speed", "read", "write-float", "active-report"])
    private.add_argument("--motor", type=parse_int, required=True)
    private.add_argument("--clear-fault", action="store_true")
    private.add_argument("--mode", type=parse_int, default=RUN_MODE_MIT)
    private.add_argument("--pos", type=float, default=0.0)
    private.add_argument("--vel", type=float, default=0.0)
    private.add_argument("--kp", type=float, default=30.0)
    private.add_argument("--kd", type=float, default=1.0)
    private.add_argument("--torque", type=float, default=0.0)
    private.add_argument("--index", type=parse_int, default=PARAM_RUN_MODE)
    private.add_argument("--value", type=float, default=0.0)
    private.add_argument("--enable-report", action="store_true")
    private.add_argument("--wait", type=float, default=0.2)
    private.set_defaults(func=cmd_private)

    cansimple = sub.add_parser("cansimple", help="CANSimple motor/node control, default node 3")
    add_common(cansimple)
    cansimple.add_argument("action", choices=["get-error", "address", "closed-loop", "idle", "clear", "vel", "pos", "torque"])
    cansimple.add_argument("--node", type=parse_int, default=3)
    cansimple.add_argument("--error-type", type=parse_int, default=0, help="CANSimple Get_Error type; 0=active errors")
    cansimple.add_argument("--vel", type=float, default=0.0, help="rad/s")
    cansimple.add_argument("--pos", type=float, default=0.0, help="rad")
    cansimple.add_argument("--torque", type=float, default=0.0)
    cansimple.add_argument("--wait", type=float, default=0.2)
    cansimple.set_defaults(func=cmd_cansimple)

    m33 = sub.add_parser("m33", help="send 0x320 commands for M33 to execute")
    add_common(m33)
    m33.add_argument("action", choices=["enable", "stop", "zero", "mode", "active-report", "target"])
    m33.add_argument("--joint", type=parse_int, required=True)
    m33.add_argument("--clear-fault", action="store_true")
    m33.add_argument("--mode", type=parse_int, default=RUN_MODE_MIT)
    m33.add_argument("--enable-report", action="store_true")
    m33.add_argument("--deg", type=float, default=0.0)
    m33.add_argument("--rpm", type=int, default=0)
    m33.add_argument("--torque-ma", type=int, default=0)
    m33.add_argument("--wait", type=float, default=0.2)
    m33.set_defaults(func=cmd_m33)

    f103 = sub.add_parser("f103", help="test STM32F103 data link")
    add_common(f103)
    f103.add_argument("action", choices=["status", "set-rate", "start", "stop"])
    f103.add_argument("--seq", type=parse_int, default=1)
    f103.add_argument("--period-ms", type=parse_int, default=20)
    f103.add_argument("--wait", type=float, default=1.0)
    f103.set_defaults(func=cmd_f103)

    raw = sub.add_parser("raw", help="send one raw standard or extended frame")
    add_common(raw)
    raw.add_argument("--id", type=parse_int, required=True)
    raw.add_argument("--ext", action="store_true")
    raw.add_argument("--data", default="")
    raw.add_argument("--wait", type=float, default=0.2)
    raw.set_defaults(func=lambda args: raw_send(args))

    return parser


def raw_send(args: argparse.Namespace) -> int:
    sock = with_socket(args)
    try:
        send(sock, CanFrame(args.id, parse_hex_bytes(args.data), args.ext))
        recv_until(sock, args.wait, None)
    finally:
        sock.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
