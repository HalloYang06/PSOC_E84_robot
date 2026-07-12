# M33 / M55 IPC And BLE Foundation

Last updated: 2026-07-12

## Ownership

- M33 owns realtime CAN, the final safety decision, motor protocol output, the BLE NUS endpoint, and the M33 side of IPC.
- M55 owns WiFi, XiaoZhi audio/voice, LVGL, and model runtime.
- BLE, M55, App, server, VLA, and simulation do not grant motion permission.
- Formal motion remains `JointTrajectory -> NanoPi -> M33 -> motor`.

## Startup Contract

1. M33 initializes M33/M55 IPC asynchronously and starts the single IPC pump.
2. The main startup context waits for the first M55 `VOICE_STATUS` snapshot.
3. Only after M55 runtime readiness does M33 power the CYW55500 Bluetooth path, perform HCI autobaud, load the controller patch, start BTSTACK/GATT, and advertise.
4. The minimal heartbeat loop starts after Bluetooth bring-up completes. If M55 is not ready within 20 seconds, Bluetooth startup is skipped and the heartbeat loop continues.

This order prevents CYW55500 Bluetooth power-up from colliding with CM55/WiFi startup.
HCI bring-up must stay on the existing main startup stack: a 2026-07-12 experiment moving it to a dynamically allocated RT-Thread stack reproduced the Secure HardFault and was reverted.

## BLE Contract

| Item | Value |
|---|---|
| Device | `OpenClaw-NUS` |
| Service | `6E400001-B5A3-F393-E0A9-E50E24DCCA9E` |
| RX | `6E400002-B5A3-F393-E0A9-E50E24DCCA9E` |
| TX notify | `6E400003-B5A3-F393-E0A9-E50E24DCCA9E` |
| Command queue | Bounded FIFO, depth 8 |
| Telemetry period | 100 ms |

Allowed commands are `heartbeat`, `stream:on`, and `stream:off`. Motion or mode commands return `ERR:readonly` and never enter the command queue.

The NUS TX mutex serializes a whole fragmented JSON frame with command acknowledgements, so acknowledgements cannot be inserted into the middle of telemetry. A full command queue returns `ERR:busy`.

## Telemetry Safety

- Telemetry is built from read-only control-layer caches.
- Motor, EMG, and heart values older than 1000 ms are emitted as zero, not reused as live values.
- The current readonly profile reports passive mode, motion disabled, and safety warning (`sf=1`).
- No synthetic demo sensor values are used by the BLE worker.

## IPC Contract

- One M33 IPC pump consumes inbound M55 messages.
- BLE callbacks and the BLE worker do not consume IPC and do not publish motion commands through IPC.
- `m55qa_status` is the primary read-only shell check; a healthy idle state has `ipc_ready=1` and `tx_pending=0`.

## Validation Boundary

BLE validation may scan, connect, subscribe, send the three allowed commands, inspect telemetry, disconnect, and confirm advertising recovery. It must not execute `move`, mode changes, motor enable, speed, position, torque, or any other motion command.
