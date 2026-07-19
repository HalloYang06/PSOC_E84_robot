# Protocol And Safety Boundaries

Last updated: 2026-06-12

This document keeps the system's communication paths and authority boundaries in one place. It is intentionally conservative: if a path is not listed as formal motion, it must not be used as formal motion.

## Authority Model

```text
App / VLA / server / M55 / MuJoCo
        |
        | suggestions, state, dry-run, shadow, debug
        v
NanoPi ROS2 bridge
        |
        | formal target frames only when enabled and safe
        v
M33 control layer
        |
        | final safety decision and motor protocol output
        v
Motors
```

Formal motion path:

```text
JointTrajectory -> NanoPi -> CAN 0x320 -> M33 -> motor bus
```

No other path should be treated as product motion.

## CAN IDs

| ID | Direction | Meaning | Notes |
|---|---|---|---|
| `0x320` | NanoPi -> M33 | Formal ROS command/target frame | Must be gated. No unexpected `0x320` in readonly product service. |
| `0x321` | NanoPi -> M33 | Heartbeat | Basic bus and M33 liveness probe. |
| `0x322` | M33 -> NanoPi | M33 status / heartbeat ACK / safety state | Do not equate liveness with motion permission. |
| `0x323` | M33 -> NanoPi | M55/model status | Suggestion-only, not motion permission. |
| `0x324` | NanoPi -> M33 | Rehab mode command, active local work | Uncommitted/current branch work; treat as experimental until compiled and hardware-tested. |
| `0x325` | M33 -> NanoPi | Rehab mode status, active local work | Uncommitted/current branch work; treat as experimental until compiled and hardware-tested. |
| `0x330~0x337` | M33 -> NanoPi | Per-slot motor telemetry | Stale flag means do not publish/use as real joint state. |
| `0x7C0` | M33 -> C8T6 | Sensor node control | C8T6 branch protocol. |
| `0x7C1` | C8T6 -> M33 | Sensor node ACK | C8T6 branch protocol. |
| `0x7C2` | C8T6 -> M33 | Sensor data | EMG/heart flags, compact payload. |
| `0x7C3` | C8T6 -> M33 | Sensor health | State, error count, queue fill. |

Older docs mention `0x300~0x310` sensor IDs. Treat those as earlier compatibility/history unless the active firmware branch explicitly uses them.

## `0x320` Boundary

`0x320` is the key frame to watch when deciding whether the system can move hardware.

Rules:

- Readonly/product services must not emit it.
- Dry-run may compute trajectories but must not emit it.
- Bench-debug may emit it only under explicit operator action.
- Clinical/product motion may emit it only after safety/prearm/freshness checks pass.
- VLA, APP, M55, and MuJoCo must not emit it directly.

When debugging, always capture whether `0x320` appeared:

```bash
timeout 2 candump -L can0,320:7FF
```

No output is the expected result for readonly services.

## Motor Status Freshness

M33 may publish motor status frames even when a motor is not fresh. This is intentional. It tells the rest of the system that the firmware is alive while still preventing stale data from becoming joint state.

Long-term rule:

```text
M33 status frame present != real joint state present.
fresh motor feedback + no stale flag == candidate real joint state.
```

NanoPi and MuJoCo shadow code should skip stale motor telemetry when publishing `/joint_states`.

## BLE NUS Path

Current M33 BLE service:

| Item | Value |
|---|---|
| Device name | `OpenClaw-NUS` |
| Service UUID | `6E400001-B5A3-F393-E0A9-E50E24DCCA9E` |
| RX characteristic | `6E400002-B5A3-F393-E0A9-E50E24DCCA9E` |
| TX characteristic | `6E400003-B5A3-F393-E0A9-E50E24DCCA9E` |
| Payload style | ASCII commands, JSON telemetry |

Recognized ASCII commands:

```text
stream:on
stream:off
heartbeat
stop
mode:passive
mode:active
mode:memory
mode:ai
mode:ai_assist
move:<app_joint_id>:<target>
```

Boundary:

- `stream:*` and telemetry are safe as status/control-plane operations.
- `stop` may map to safe/passive behavior.
- `mode:*` must not be treated as formal motion permission by itself.
- `move:*` is legacy/bench-debug until it is routed through the same safety checks as `0x320`.

## M33 / M55 IPC Path

The model path is:

```text
M33 snapshot -> M55 model/input bridge -> TFLM or rule model -> M33 model bridge -> CAN 0x323 -> NanoPi
```

Boundary:

- `0x323` is a model result/status frame.
- It may carry confidence, detection, or result codes.
- It is not a motion permission.
- Any future assistive behavior must still pass through M33 safety and explicit mode arbitration.

## NanoPi / ROS2 Boundary

NanoPi owns Linux-side bridging and ROS2 integration. It should:

- parse M33 `0x322` and motor telemetry,
- publish safety/motor/model state,
- publish `/joint_states` only from fresh feedback,
- keep product readonly service with target TX disabled by default,
- explicitly gate any trajectory-to-`0x320` conversion.

Product service invariant:

```text
enable_target_tx=false by default
```

## MuJoCo Boundary

MuJoCo is a shadow/dry-run environment. It may:

- display real fresh joint state,
- replay logs,
- validate candidate trajectories,
- support operator understanding.

It must not be described as:

- realtime safety,
- physical emergency stop,
- final authorization,
- proof that hardware can move safely.

## APP Boundary

The APP is a user interface and data display path. It may:

- request modes,
- display telemetry,
- send stream/heartbeat/debug commands,
- collect patient/session/training data,
- send high-level requests to NanoPi/server.

It should not be the formal motion authority. Direct APP `move:*` commands should be removed from product UX or kept behind explicit bench-debug UI.

## Build Profiles

The project needs named profiles instead of relying on ad-hoc macro edits:

| Profile | Motion behavior | Intended use |
|---|---|---|
| `bench-debug` | Allows explicit bench motion under operator control | Bring-up and motor tests |
| `readonly-product` | Publishes state, never emits motion targets | Demo, monitoring, product startup |
| `clinical-prearm` | Motion only after full prearm and fresh feedback | Future formal wearable path |

Minimum compile-time checks should prevent enabling bench and clinical motion simultaneously.

## Hardware Debug Order

When CAN or motor behavior is wrong, debug in this order:

1. Power, ground, transceiver enable, CANH/CANL, termination.
2. NanoPi `can0` bitrate and error counters.
3. M33 direct CAN register state.
4. `0x321 -> 0x322` heartbeat.
5. M33 `0x330~` motor status publishing.
6. Raw vendor motor feedback.
7. Fresh/stale translation.
8. ROS parser and `/joint_states`.
9. Only then trajectory or model integration.

If the bus is no-ACK or bus-off, stop changing ROS/MuJoCo/model code until physical CAN evidence is healthy again.

