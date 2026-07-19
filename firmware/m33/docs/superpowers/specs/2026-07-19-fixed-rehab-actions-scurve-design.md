# Fixed Rehab Actions With Smooth Motion Design

Date: 2026-07-19

## Goal

Build one isolated passive-training path for the rehabilitation arm: the App only selects a small set of fixed actions, and the M33 firmware turns those actions into smooth, synchronized, safety-checked motion. This path is for stable motion acceptance first; it must not mix with assist, resist, free trajectory, cloud plan, ROS, NanoPi, or existing AI-plan features.

## User-Facing Product Scope

The App adds a dedicated mobile page named `平稳动作训练`.

The page shows anatomical action names only:

- `肘部屈伸`
- `肩部平转`
- `协同训练`
- `肩部前后`

The `肩部前后` card is visible but disabled with the text `尚未完成校准，暂不可用`. The page must not show motor numbers, raw ranges, engineering protocol names, current limits, velocity limits, controller names, or debug terms. Training is fixed at `3次往返`; the user cannot edit amplitude, count, velocity, current, or trajectory points.

The page copy is:

- Title: `平稳动作训练`
- Subtitle: `选择一个固定动作，设备会按平缓节奏完成被动训练`
- Connection state: `设备已连接 / 可以开始训练`
- Primary action: `开始训练`
- Running preview: `第 2 / 3 次`, `平稳运行中`, `暂停`, `停止训练`
- Safety note: `离开页面、蓝牙断开或设备异常时，训练会自动停止；恢复训练需要重新确认。`

The App page is designed through Stitch MCP using the Serene Recovery style. As of this spec, Stitch read APIs work, but long-running write APIs still disconnect near 60 seconds and have not produced the page screen. Implementation may proceed only with this written UI contract; the visual Stitch artifact remains a tool-level blocker to resolve before final UI acceptance.

## Internal Joint Mapping

The firmware may use internal joint identifiers, but they never appear in App text.

- Internal joint 4: shoulder fore/aft, uncalibrated placeholder, rejected by firmware for motion.
- Internal joint 5: elbow, hard raw range `6.000` to `8.264` rad, safe endpoints `6.226` to `8.038` rad.
- Internal joint 6: shoulder planar rotation, hard raw range `3.532` to `5.101` rad, safe endpoints `3.689` to `4.944` rad.

The executable fixed profiles are:

- `elbow_flex_extend`: joint 5 only, safe endpoint A to B and back.
- `shoulder_planar`: joint 6 only, safe endpoint A to B and back.
- `coordinated_elbow_shoulder`: joints 5 and 6 synchronized over the same segment time.
- `shoulder_fore_aft_placeholder`: rejected because calibration is incomplete.

## Firmware Architecture

The M33 owns the canonical motion path:

`App fixed action adapter / future MuJoCo adapter -> unified motion command -> safety trajectory layer -> joint limits -> jerk-limited synchronized interpolation -> 20 ms CSP setpoints -> motor drivers`

MuJoCo support is not implemented in this phase, but future MuJoCo commands must enter through the same unified motion command and safety trajectory layer. No caller may stream direct motor targets around the smooth trajectory layer.

## Motion Algorithm

Use a jerk-limited S-curve trajectory generator on the M33. Do not add LADRC for this phase because the existing motors already have internal position, velocity, and current loops, and the current ADRC code is tied to assist-current trimming rather than identified position control.

Default limits:

- Maximum velocity: `0.12 rad/s`
- Maximum acceleration: `0.20 rad/s^2`
- Maximum jerk: `0.50 rad/s^3`
- Sample period: existing 20 ms rehab service tick, sampled from absolute time
- Arrival condition: position error at or below `0.03 rad` for 5 consecutive cycles
- Dwell time at each endpoint: 500 ms
- Segment timeout: theoretical segment duration plus 5 seconds

For multi-joint action, compute each joint distance, choose the longest required segment time, and time-scale the shorter joint trajectories so all moving joints start and arrive together. Every sampled setpoint must be clamped to the safe endpoint envelope before it reaches the motor driver.

## Runtime State Machine

Each action uses this state machine:

`IDLE -> PRECHECK -> CSP_PREPARE -> ALIGN_FROM_CURRENT -> MOVE_A -> DWELL_A -> MOVE_B -> DWELL_B -> DECEL_STOP -> COMPLETE`

The action performs 3 full round trips unless stopped or faulted. `ALIGN_FROM_CURRENT` starts the generated trajectory from measured current position so the first command does not jump to a hardcoded endpoint.

Pause, page leave, BLE disconnect, and heartbeat timeout trigger jerk-limited deceleration stop, then latch paused state. Resume requires an explicit user confirmation and a fresh precheck.

Stale feedback, hard-limit violation, overspeed, motor fault, severe following error, or service loop gap triggers group stop and latches fault.

Fault thresholds:

- Feedback stale above 100 ms
- Speed above `0.35 rad/s`
- Following error warning at or above `0.10 rad`
- Following error trip at or above `0.20 rad` for 100 ms, or immediate trip at or above `0.40 rad`
- Service loop gap above 100 ms

Commissioning current limit starts at 1.0 A, may be raised to 1.5 A after bench validation, and must not exceed 2.0 A. The App cannot change this value.

## Control-Layer Change

The current control path reconfigures the motor run mode, waits, enables, writes parameters, and sends a target inside `control_motor_position_control_with_current_limit()` on every call. That behavior is a likely source of vibration and desynchronization.

Split the control behavior into:

- One-time CSP prepare for each involved motor during `CSP_PREPARE`.
- High-rate setpoint-only updates during MOVE states.
- Explicit group stop on fault or commanded stop.

Existing assist, resist, ROS, NanoPi, and memory-playback paths must not be refactored into this feature.

## BLE Contract

Extend the existing strict `rehab_ble_v1` command path with fixed profile IDs. The App sends only a fixed profile selection plus request metadata and heartbeat. It does not send arbitrary trajectory points, raw limits, current, velocity, acceleration, or jerk.

Firmware validates:

- Known fixed profile ID
- Device connected and BLE runtime ready
- No conflicting current owner
- Fresh heartbeat lease
- Profile not disabled
- Safe endpoint envelope available

Every accepted command returns an ACK. Every rejected command returns a reason that the App maps to user-safe Chinese text without exposing internal identifiers.

## App Implementation Scope

Update the web App source and the Android WebView mirror once the Stitch page structure is accepted:

- `F:\wt\platform-ai-latest\apps\web\public\rehab-arm-mobile\`
- `F:\wt\platform-ai-latest\apps\mobile\rehab-arm-android\www\`

The App repository baseline has a known risk: the local checkout is stale against `origin/app/rehab-arm-mobile-stitch`, and previously documented NUS commits were not present locally. Before implementation, update or reconcile the App branch so the BLE transport used by the page matches the current M33 `rehab_ble_v1` path.

## Testing Strategy

Host tests must cover:

- S-curve endpoint continuity, monotonic segment progress, velocity, acceleration, and jerk bounds.
- Absolute-time sampling under 20 ms ticks, late cycles, and tick wrap.
- Single-joint and two-joint synchronized duration.
- Start-from-current alignment without target jump.
- Disabled shoulder fore/aft profile rejects without actuation.
- State machine transitions for 3 round trips, dwell, pause, stop, feedback stale, loop gap, following error, overspeed, and fault latch.
- Control-layer prepare-once versus setpoint-only updates.
- BLE parser acceptance for fixed profiles and rejection for arbitrary parameters.
- App UI forbidden-word checks for motor numbers and engineering terms.
- App command, ACK, heartbeat, pause, stop, and disconnect behavior.

Firmware verification must include the existing host test suite and an M33 SCons build for the selected motion profile. Hardware acceptance starts with one single-joint fixed action at the 1.0 A commissioning limit before enabling coordinated motion.
