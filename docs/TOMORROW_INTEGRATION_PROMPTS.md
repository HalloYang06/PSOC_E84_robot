# Tomorrow Integration Prompts

Date target: 2026-05-28

This document is the shared prompt and checklist for the next integration day. Use it with the platform AI, App AI, and the ROS/NanoPi agent so all three sides follow the same safety boundaries and data contracts.

## Non-Negotiable Safety Rules

- This is a wearable rehabilitation exoskeleton. Human safety is higher priority than demos.
- No human wearing during first integration.
- M33 remains the final safety authority.
- App, platform, NanoPi, Linux workstation, VLA, and Python tools must not bypass M33.
- Direct NanoPi motor CAN control remains debug-only and must not enter formal launch.
- Any profile, BLE package, trajectory, or replay artifact that fails validation must not be used for motion.
- Server/platform is not a real-time control loop.
- App real-time path is BLE to M33. NanoPi/OpenClaw HTTP is high-level service only.

## Shared Architecture Reminder

```text
Linux simulation host:
  URDF/MuJoCo/RViz, replay, planning, data review

NanoPi:
  ROS2 bridge, M33 CAN bridge, telemetry aggregation, camera/data gateway

M33:
  realtime safety state machine, limits, estop, heartbeat timeout, motor control

C8T6:
  EMG/heart/IMU sensor node, reports to M33/CAN

App:
  BLE to M33 for local training interaction and approved safety package

Platform:
  device data workbench, profile review, data assets, annotation, model/training management
```

## Prompt For Platform AI

You are the platform development AI for a robotics development and data platform. Work in the existing AI collaboration platform repo. Do not rewrite the platform from scratch. Preserve NPC/AI employee features and only index/use them from the robot device workflow.

Goal for this integration day:

Build or adjust platform features so the platform can support generic Linux robot boards and this rehab arm project through data, profile review, and annotation workflows.

Hard boundaries:

- Do not implement real-time motor control from the platform.
- Do not send CAN frames.
- Do not bypass M33.
- Do not remove NPC workspace/AI employee features.
- Do not create demo-only pages that pollute the product.
- Keep UI simple, dense, and user-focused.

Required platform capabilities:

1. Linux board device page
   - Scan/register Linux boards such as NanoPi.
   - Show board identity, online state, capabilities, last sync, and data quality.
   - Allow user to start/stop data sync manually.
   - Show camera keyframes when present.
   - Show `/joint_states`, `/rehab_arm/motor_state`, `/rehab_arm/safety_state`, and `/rehab_arm/sensor_state`.

2. Patient/profile workflow
   - Import or display `patient_device_profile_v1`.
   - Display validation report from `patient_device_profile_validation_v1`.
   - Display change report from `patient_device_profile_change_report_v1`.
   - Display BLE package draft `ble_m33_safety_package_v1`.
   - Treat all validation/change warnings as review items. Do not silently approve.

3. Data/annotation workflow
   - Read `rehab_arm_manifest_v1`, `rehab_arm_recording_quality_v1`, `rehab_arm_annotation_queue_v1`, and `rehab_arm_dataset_index_v1`.
   - Show skipped sessions and reasons.
   - Allow data assets to enter annotation only if quality gate passes.
   - Keep this generic for robots, not hardcoded only for medical rehab.

4. 3D robot preview
   - Use Three.js + URDF loader when URDF is available.
   - Bind joint colors to motor temperature/fault/limit state.
   - Camera controls must work.
   - UI must not be cluttered. Put advanced tools in drawers or secondary panels.

Integration source contracts:

- `docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md`
- `docs/PATIENT_DEVICE_PROFILE_PROTOCOL_V1.md`
- `docs/SERVER_SYNC_API_DRAFT.md`
- `docs/USER_MANUAL.md`

Validation:

- Run frontend build/tests.
- Open the actual page in browser.
- Click main buttons manually, not only through scripts.
- Capture screenshots for user review.
- Commit and push platform changes to the correct branch.

Report back:

- What page(s) changed.
- What data contracts are supported.
- Screenshots path.
- Tests/build result.
- Any missing backend/API fields.

## Prompt For App AI

You are the App development AI for the rehab arm project. The App connects to M33 over BLE for local real-time interaction. The App may use HTTP/server only for accounts, history, reports, data sync, or high-level services; it must not depend on NanoPi for local safety commands.

Goal for this integration day:

Prepare the App to consume the shared Patient Device Profile and send an approved safety package to M33 over BLE in the future. For now, implement only UI/workflow and dry-run parsing unless the user explicitly asks to test real BLE.

Hard boundaries:

- Do not directly control motors.
- Do not send raw CAN.
- Do not bypass M33 safety.
- Do not treat draft/pending profiles as executable.
- Do not invent a separate App-only profile schema.

Required App capabilities:

1. BLE M33 device flow
   - Scan/connect to M33 BLE device.
   - Display connection state.
   - Display M33 safety state and profile version when available.
   - Provide local pause/stop/emergency request UI, but mark final authority as M33.

2. Profile flow
   - Load/display `patient_device_profile_v1`.
   - Display `patient_device_profile_validation_v1`.
   - Display `patient_device_profile_change_report_v1`.
   - Display `ble_m33_safety_package_v1`.
   - Only allow package-send UI when package `ok=true` and `profile_status` is `approved` or `active`.

3. Training UI
   - Show patient name/ref, bound robot/device, mode, ROM, velocity limits.
   - Show clear active/passive/memory/resistance mode selection.
   - Show prominent emergency stop request button.
   - Show warnings when ROM widened, velocity increased, or profile version changed.

4. BLE package future contract
   - Treat `ble_m33_safety_package_v1` as the future payload source.
   - Include placeholders for signature, expiry, ack, fragmentation, retry, and failure display.
   - Do not implement final write until M33 BLE characteristic and ack contract are confirmed.

Integration source contracts:

- `docs/PATIENT_DEVICE_PROFILE_PROTOCOL_V1.md`
- `docs/APP_CONNECTION_GUIDE.md`
- `docs/USER_MANUAL.md`

Validation:

- Build App.
- Run UI locally.
- Walk through profile import/review/send-disabled flow as a user.
- Capture screenshots.
- Commit and push App changes to the correct branch.

Report back:

- BLE screens implemented.
- Profile/package screens implemented.
- What BLE UUIDs/characteristics are still missing.
- Build/test result.
- Screenshots path.

## Prompt For ROS/NanoPi/Linux Agent

You are the ROS/NanoPi/Linux integration agent for the rehab arm project. Work in `D:\RT-ThreadStudio\workspace\_nanopi_rosnode_usbcan` and on the Linux simulation host/NanoPi through SSH when available.

Goal for this integration day:

Bring up the standard robot development path: Linux simulation host, NanoPi ROS data bridge, C8T6 sensor data, M33 safety state, and platform/App data contracts. Do this step by step and test after each step.

Hard boundaries:

- Do not work on M33 firmware unless user explicitly says to and can flash/reset.
- Do not move motors during first data bring-up.
- Do not use direct NanoPi motor CAN in formal path.
- Do not send trajectories until M33 reports a formal safe state and the user explicitly allows motion.
- Do not let Python be the final safety loop.

Bring-up order:

1. Git sync
   - Pull latest branch `feature/rehab-arm-ros2-architecture`.
   - Check `git status`.
   - Do not stage unrelated dirty files.

2. Linux simulation host
   - Install/check ROS2 environment.
   - Build `rehab_arm_ros2_ws`.
   - Run unit tests available on host.
   - Prepare RViz/MuJoCo subscriber path.
   - Use `jsonl_replay_node.py` first before live hardware.

3. NanoPi basic checks
   - SSH to NanoPi.
   - Confirm `can0` exists, classic CAN 1Mbps, `ERROR-ACTIVE`.
   - Confirm ROS package executables with `ros2 pkg executables rehab_arm_psoc_bridge`.
   - Do not assume executable names.

4. M33 status checks
   - Heartbeat `0x321 -> 0x322`.
   - Parse `/rehab_arm/safety_state`.
   - If `bench_armed`, treat as not wearable-safe.
   - If no formal `motion_allowed=true`, do not send trajectory.

5. C8T6 sensor checks
   - Capture CAN frames.
   - Verify `0x7C2` sensor frame target and `0x7C3` health frame.
   - Convert into `/rehab_arm/sensor_state` JSON if bridge support exists; otherwise capture raw logs and document gap.

6. Data collection
   - Start `data_recorder_node`.
   - Record `/joint_states`, `/rehab_arm/motor_state`, `/rehab_arm/safety_state`, `/rehab_arm/sensor_state`, `/rehab_arm/camera_keyframe` if available.
   - Run `check_recording.py`, `validate_recording_quality.py`, `build_manifest.py`, `build_dataset_index.py`.

7. Platform/App handoff artifacts
   - Generate or validate:
     - `patient_device_profile_validation_v1`
     - `patient_device_profile_change_report_v1`
     - `m33_safety_profile_v1`
     - `ble_m33_safety_package_v1`
     - `rehab_arm_dataset_index_v1`

8. Only after data path is stable
   - Test replay in Linux/RViz/MuJoCo.
   - Only test motion when user is present, device is not worn, M33 formal gate allows it, and clear target/limits are agreed.

Expected commands:

```bash
ros2 run rehab_arm_psoc_bridge validate_patient_profile.py PROFILE.json --pretty
ros2 run rehab_arm_psoc_bridge review_patient_profile_change.py OLD.json NEW.json --pretty
ros2 run rehab_arm_psoc_bridge export_m33_safety_subset.py PROFILE.json --pretty
ros2 run rehab_arm_psoc_bridge build_ble_m33_safety_package.py PROFILE.json --approved-by clinician_001 --approved-at 2026-05-27T10:00:00+08:00 --expires-at 2026-05-28T10:00:00+08:00 --pretty
ros2 run rehab_arm_psoc_bridge jsonl_replay_node.py --ros-args -p recording_path:=SESSION.jsonl
```

Report back:

- Hardware online/offline status.
- CAN state and observed frame IDs.
- ROS topic list and message samples.
- Recording quality report.
- Platform/App artifacts generated.
- Exact blocker if any.

## One-Day Integration Checklist

Use this checklist in order.

1. No human wearing hardware.
2. Confirm power and cooling.
3. Confirm Git branches for all repos.
4. Confirm NanoPi reachable.
5. Confirm Linux simulation host reachable.
6. Confirm M33 BLE visible to App.
7. Confirm `can0 ERROR-ACTIVE`.
8. Confirm M33 heartbeat.
9. Confirm C8T6 `0x7C2/0x7C3`.
10. Confirm recorder JSONL works.
11. Confirm quality report works.
12. Confirm dataset index works.
13. Confirm platform can ingest/display data.
14. Confirm App can display profile/package dry-run.
15. Confirm replay node can publish `/joint_states`.
16. Confirm RViz/MuJoCo can consume `/joint_states`.
17. Decide whether any motion test is allowed.

## Stop Conditions

Stop and document if any of these happen:

- `can0` enters bus-off or error-passive repeatedly.
- M33 heartbeat is missing or malformed.
- C8T6 health is missing.
- App/platform/NanoPi disagree on active profile version.
- `motion_allowed` semantics are unclear.
- Any profile/package validation fails.
- Motor moves unexpectedly.
- Board overheats.
- User is not physically able to power off/reset when motion testing is requested.
