# Project Progress

## 2026-07-21 - Three-motor eye-to-hand capture bring-up

Completed:

- Added a fixed-camera eye-to-hand calibration utility with RANSAC rigid fitting, independent validation, stereo-calibration binding, atomic sessions, and explicit motor set `4/5/6`.
- Added `capture-raw` for synchronized three-motor angles and independent stereo gripper XYZ before three-joint forward kinematics is available.
- Changed the live RK3576 pipeline to infer the gripper in both cameras and to publish end-effector camera XYZ only after a valid left/right stereo match. The two eyes share one serialized RKNN runtime.
- Deployed the scripts to NanoPi `10.101.106.82`, restarted only `rehab-vla-vision.service`, and initialized `/home/pi/rehab_arm_calibration/session_3motor_20260721.json`.

Validated:

- Host calibration/vision tests: 13 passed; focused eye-to-hand tests after raw-capture addition: 6 passed.
- NanoPi vision service active; fresh context observed with approximately 74 ms heavy detection pipeline time after warm-up.
- Empty/partial-gripper preflight correctly recorded `0/5` samples and left the session observations empty.

Open:

- Current live frame does not show one clear gripper tip fully inside both images, so no real pose has been accepted yet.
- ROS `/joint_states` and `/rehab_arm/motor_state` had no live messages during this check. Until feedback returns, the operator must enter measured 4/5/6 angles explicitly.
- Implement and validate the exact three-joint forward-kinematics/visual-zero mapping before converting raw angle samples to `base_link XYZ` and solving the transform.

## 2026-07-21 - NanoPi preferred demo hotspot profile

Completed:

- Located the live NanoPi M5 at `10.17.66.82` on `wlan0`; hostname evidence is `NanoPi-M5`.
- Added the persistent NetworkManager profile `cal_network` with autoconnect enabled and priority `100`.
- Kept both existing `RedmiK70E` profiles as fallback connections with autoconnect enabled and priority `10`.
- Confirmed the active connection remained `RedmiK70E 1` because `cal_network` was not broadcasting during configuration. No kernel, driver, CAN, motor, or service configuration was changed.

Next:

- When `cal_network` is broadcasting, NetworkManager should prefer it automatically. Re-discover the DHCP address from the PC on the same hotspot and verify the active profile after switching.
- Wi-Fi credentials are device-local and are intentionally not recorded in Git.

## 2026-07-21 - Competition-day launch package

Completed:

- Corrected the device availability assessment: the operator PC was on `192.168.111.0/24`, so failures to reach `192.168.3.x` were routing evidence, not proof that NanoPi or MuJoCo was powered off.
- Added a one-page run card and a non-motion launcher for cloud status, offline evidence playback, plan opening, and backup packaging.
- Kept all real-motion ownership in the existing supervised director/ROS/M33 path; the new launcher cannot publish ROS, CAN, or motor commands.

Next: connect to the device router, rerun status/preflight, then rehearse and freeze L2 or downgrade to L3/L4.

## 2026-07-20 - Competition live demo plan

Completed:

- Audited the canonical architecture, current cloud availability, NanoPi vision baseline, MuJoCo/ROS history, EMG model evidence, App boundary, historical director scripts, and offline synchronized videos.
- Added a five-minute competition script with L1 full-live, L2 hybrid, L3 digital-twin, and L4 offline-evidence modes.
- Added night-before and 30-minute preflight gates, fault downgrade rules, operator roles, exact rehearsal commands, and judge Q&A.

Current external state:

- Cloud API and control page returned HTTP 200 on 2026-07-20.
- Known NanoPi LAN addresses and the MuJoCo host `192.168.3.34` were offline during this audit, so L1/L2 remain unproven until the night-before hardware rehearsal.

Plan: `docs/demo/competition-live-demo-plan-20260721.md`.

## 2026-07-20 - NanoPi RK3576 vision baseline sync

Completed:

- Synchronized the latest committed NanoPi VLA-V sequence from
  `wenjunyong666/ai-:feature/rehab-arm-rk3576-npu-20260712` through `b03ea772`.
- Added the dual-camera capture, RKNN benchmark, RKNN/ONNX upload loop,
  provisional natural-feature calibration, dense stereo fallback, and their
  algorithm tests under `tools/nanopi/vision`.
- Promoted three previously deployed but untracked helper sources to a canonical
  tracked baseline: the persistent capture daemon, OpenCV DNN probe, and CPU
  target inference helper.
- Preserved the control boundary: this package produces visual evidence only
  and does not publish trajectories, CAN frames, or motor commands.

Validated:

- Python syntax compilation: pass.
- NanoPi stereo algorithm tests: 10 passed.
- Repository guard tests: 36 passed.

Not yet verified:

- The NanoPi was offline at the known LAN addresses during this sync, so current
  device files, service units, camera enumeration, NPU state, and live FPS were
  not re-audited.
- C++ helpers were not compiled on this Windows host because the target OpenCV
  and RK3576 runtime are device-side dependencies.
- `rehab-rknpu-load.service` and `rehab-vla-vision.service` unit files still need
  to be recovered from the device as tracked deployment assets.

Next smallest task: when the NanoPi is online, compare hashes for the deployed
vision files, recover the two service units and environment template without
copying secrets, then rerun the live 8 FPS/NPU/upload evidence check.
