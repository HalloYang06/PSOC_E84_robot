# Project Long-Term Briefing

Last updated: 2026-06-12

This project is a medical rehabilitation robotic arm system built around Infineon PSoC Edge E84, external motor drivers, a NanoPi ROS2 bridge, an Android app, a sensor node, and model/VLA side channels.

The important long-term rule is simple:

```text
AI, app, server, M55, and simulation may suggest or display state.
Real hardware motion must be approved by M33.
```

## One-Sentence Architecture

The intended formal motion path is:

```text
JointTrajectory -> NanoPi ROS2 bridge -> CAN 0x320 -> M33 safety/control layer -> motor bus
```

Everything else must be treated as state, suggestion, dry-run, shadow simulation, or explicit bench-debug.

## Device Responsibilities

| Device / subsystem | Responsibility | Current maturity |
|---|---|---|
| M33 | Realtime CAN owner, motor protocol gateway, safety gate, status publishing, BLE near-field service, M33/M55 bridge | Main firmware path exists; control layer is powerful but large |
| M55 | Audio/WiFi/model runtime side, M33/M55 IPC consumer/producer | Data path and TFLM runtime proven; real rehabilitation model still pending |
| NanoPi | SocketCAN, ROS2 bridge, readonly product service, status parsing, camera/server gateway | Architecture and tests are strongest on `feature/rehab-arm-ros2-architecture` |
| C8T6 | EMG/heart sensor collection and CAN sensor node | Sensor protocol and event-driven firmware exist on `C8T6` |
| Android app | BLE UI, patient/training workflows, data display, debug screens | Feature-rich, but transport/protocol variants need cleanup |
| MuJoCo / Linux host | Shadow simulation, dry-run validation, visualization | Useful for state shadow and planning validation, not a safety loop |
| VLA/server | High-level task interpretation and data fusion | Suggestion-only; must not directly control CAN or motors |
| PCB/hardware assets | Board and wiring reference | Useful reference, not executable system truth |

## Current M33 Checkout

Current local branch during this review:

```text
codex/m33-can-busoff-guard
```

Important files:

| Path | Purpose |
|---|---|
| `applications/main.c` | M33 app startup and main loop |
| `applications/control/control_layer.c` | Main CAN/control/safety implementation |
| `applications/control/control_layer_cfg.h` | Central control constants, CAN IDs, motor mapping, safety profile switches |
| `applications/control/sensor.c` | C8T6/sensor CAN parsing and sensor control helpers |
| `applications/m33/app_ble_service.c` | BLE NUS ASCII command parser and JSON telemetry |
| `applications/m33/bt_app_gatt_handler.c` | GATT/NUS RX/TX handling |
| `applications/m33/m55_model_bridge.c` | M55 model result to M33/CAN bridge |
| `applications/m33/m55_model_input_bridge.c` | M33 sensor/motor snapshot path to M55 |
| `libraries/HAL_Drivers/drv_can.c` | Infineon CAN driver and direct-send bus-off guard |

Known local uncommitted work at the time of this briefing:

```text
applications/control/control_layer.c
applications/control/control_layer_cfg.h
applications/m33/control_manager.h
applications/control/rehab_mode_manager.c
applications/control/rehab_mode_manager.h
docs/CAN_MOTOR_BRINGUP_RETROSPECTIVE_20260605.md
tools/test_rehab_mode_static.py
```

Treat those files as active work, not settled product behavior.

## Safety Boundary

The M33 control layer is the authority for motion. The following paths must remain side channels unless explicitly converted into the formal path:

- BLE `move:*` commands from the phone.
- OpenClaw or server commands.
- M55 model outputs and confidence scores.
- VLA task plans.
- MuJoCo shadow states.
- NanoPi debug tools such as direct CAN helpers.

For product or clinical builds, motion must fail closed unless the firmware has:

- fresh motor feedback for required joints,
- no active motor fault,
- confirmed joint limits,
- confirmed speed/torque/current limits,
- heartbeat and prearm checks appropriate to the deployment,
- no stale status being used as a trajectory origin,
- an explicit profile that is not bench-debug.

## Current Strengths

- The project has a good high-level safety rule: M33 is final authority.
- CAN bring-up history is rich and evidence-based.
- M33 status/fresh/stale semantics are heading in the right direction.
- NanoPi ROS2 branch has useful parser tests and product readonly safety checks.
- M33/M55 IPC and TFLM runtime chain have been proven as a data path.
- C8T6 sensor firmware has a clean event-driven CAN protocol.
- APP already has a BLE NUS path compatible with the M33 NUS UUIDs.

## Current Risks

### Demo Data In Main Loop

`applications/main.c` still calls `sensor_fill_demo_data()` in the main loop. BLE telemetry can therefore look alive even when real sensors are not feeding the displayed data. Any documentation or UI using this data must label it as synthetic until replaced with real control-layer sensor/motor state.

### Two Control Worlds

There is a small `applications/m33/control_manager.*` world with three joints and a larger `applications/control/control_layer.*` world with seven motor slots and ROS mapping. Long-term code should not let these two disagree. New real motion should go through the control layer.

### Joint ID Confusion

The system contains at least three ID spaces:

- ROS joint index,
- M33 motor slot,
- vendor motor/node ID.

The public M33 motor API generally expects 1-based M33 joint IDs. Older app/BLE helpers use 0-based app joint IDs. Never pass IDs across this boundary without an explicit mapping.

### Bench Profile Defaults

`CONTROL_DEVELOPMENT_BENCH_MOTION_ENABLE` is enabled in the current M33 config. That is reasonable for a bench branch, but product/clinical builds need a separate profile that defaults to logging-only or readonly until prearm is satisfied.

### Large Control Layer

`control_layer.c` currently combines CAN transport, protocol encoding, feedback parsing, ROS command parsing, safety gates, telemetry publishing, shell commands, and sensor routing. It should be split only after contract tests are in place.

### APP Transport Drift

The APP branch contains BLE NUS, Bluetooth SPP, and binary-frame SPP managers. The current M33 firmware exposes BLE NUS. Long-term APP docs and code should present BLE NUS as the main path and mark SPP/binary frame paths as legacy/debug unless revived deliberately.

## Recommended Next Work

1. Make `docs/文档导航.md` the normal entry point.
2. Move synthetic sensor output behind an explicit demo macro or separate demo build.
3. Route BLE telemetry from real control-layer motor/sensor state where possible.
4. Make BLE `move:*` bench-debug only, or remove it from product UI.
5. Add host-side contract tests for:
   - CAN `0x320` parser,
   - ROS joint to M33 motor slot mapping,
   - stale/fresh motor telemetry,
   - safety status payload `0x322`,
   - model status payload `0x323`,
   - clinical vs bench compile-time profile.
6. Split `control_layer.c` gradually after tests:
   - CAN router,
   - motor protocol adapters,
   - ROS command parser,
   - safety/prearm gate,
   - telemetry publisher,
   - shell/debug commands.
7. Align APP protocol docs with current BLE NUS and M33 safety boundary.
8. Turn M55 model output into a versioned result schema instead of overloading demo fields.
9. Keep NanoPi product service readonly by default and require tests proving no unexpected `0x320`.

## What Not To Claim Yet

Do not claim these until hardware evidence proves them:

- Full 6DOF clinical closed-loop control is complete.
- Real EMG rehabilitation model is trained and validated.
- VLA can safely control the arm.
- APP direct motion is a production control path.
- M55 model confidence is a motion permission.
- MuJoCo shadow is a realtime safety loop.
- Stale M33 motor status is a real joint position.

## Validation Snapshot

During the documentation review, the existing static rehab-mode contract test passed:

```powershell
python tools/test_rehab_mode_static.py
```

`git diff --check` did not report whitespace errors. It did warn that Git may convert LF to CRLF in some modified files when they are next touched.

Full firmware build was not run in this review because the local RT-Thread Studio/toolchain path is environment-specific.
