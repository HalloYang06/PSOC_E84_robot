# M33 CAN / NanoPi Bring-up Handoff

Date: 2026-05-21
Branch: M33

## Goal

NanoPi runs ROS and talks to the shared 1 Mbps CAN bus. M33 is the realtime controller for motor control and safety checks. M55 will later process sensors / edge AI and return results to NanoPi, likely through M33-side IPC and CAN/ROS feedback.

Current bus nodes:

- NanoPi with MCP2518FD SocketCAN
- Infineon M33
- STM32C8T6 sensor node
- 7 motor nodes

## M33 Changes In This Pass

Files changed:

- `applications/m33/can_driver.c`
- `applications/control/control_layer.c`
- `applications/control/control_layer_cfg.h`

Behavior:

- `can_driver_init()` now starts `control_layer_init("can0")` automatically during M33 boot.
- Motor joint count is set to 7, with default motor IDs `0x01` through `0x07`.
- NanoPi heartbeat is supported:
  - RX: standard CAN ID `0x321`
  - TX: standard CAN ID `0x322`
- STM32C8T6 sensor IDs are aligned to the actual sensor-node source:
  - EMG: `0x300`
  - Heart / SpO2: `0x301`
  - IMU accel: `0x302`
  - IMU gyro: `0x303`
  - Sensor status: `0x304`
  - Sensor control: `0x310`
- EMG parsing now accepts the STM32C8T6 payload format: two little-endian float values in millivolts.

## Expected M33 Boot Log

After flashing, M33 should print lines like:

```text
[m33] init step8 can_driver_init
[can_driver] start control layer on can0
[control] init step1 dev=can0
[control] init step6 direct pdl can init
[control] init step11 threads started
[control] init done on can0, motor_count=7, ros_cmd_can_id=0x320
[can_driver] control layer ret=0
```

If it stops before `control layer ret=0`, keep the full serial log.

## NanoPi Quick CAN Tests

Bring up CAN on NanoPi:

```bash
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up
ip -details link show can0
```

Watch bus:

```bash
candump can0
```

Send NanoPi heartbeat to M33:

```bash
cansend can0 321#01
```

Expected response from M33:

```text
can0  322   [8]  A5 01 07 00 xx xx xx xx
```

Meaning:

- `A5`: M33 heartbeat ACK marker
- `01`: echoed NanoPi sequence byte
- `07`: M33 configured motor count
- last 4 bytes: M33 RT-Thread tick, little-endian

## ROS Command Frame

NanoPi to M33 motor command still uses standard CAN ID `0x320`.

Payload:

```text
Byte0: cmd
Byte1: joint_id, 1..7
Byte2..7: command payload
```

Command values:

- `0x01`: enable
- `0x02`: stop, Byte2 = clear_fault
- `0x03`: set target, Byte2..3 pos 0.1 deg, Byte4..5 rpm, Byte6..7 torque mA
- `0x04`: set mode, Byte2 = mode
- `0x05`: set zero
- `0x06`: active report, Byte2 = enable

Do not send enable / target frames until motor power, IDs, termination, and emergency-stop behavior are confirmed.

## Local Build Note

On this computer, `python -m SCons -j4` starts but fails before compile because `rtconfig.py` points toolchain `EXEC_PATH` at `C:\Users\XXYYZZ`, which does not exist here. Compile from the RT-Thread Studio machine with the correct toolchain path.

## Next Step

1. Flash this M33 build.
2. Capture the full serial boot log.
3. From NanoPi, send `cansend can0 321#01`.
4. Confirm whether `candump can0` sees `322#A50107...`.
5. Only after the heartbeat path works, test C8T6 sensor frames and then motor probe / enable commands.
