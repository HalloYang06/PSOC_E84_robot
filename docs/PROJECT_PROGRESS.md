# Project Progress

## 2026-07-21 - Decoupled live camera preview from dashboard polling

Completed:

- Kept the full rehab-arm dashboard poll at 2 seconds and added a vision-page-only 350 ms refresh for the two latest keyframe file endpoints.
- The preview timer updates only the two Stitch iframe image elements; it does not rerender the full control room, create a frame backlog, or run while another module/tab is active.
- Applied the same scoped compatibility change to the historical cloud runtime source, backed up the prior cloud file, rebuilt, and restarted Web/API with build label `rehab-camera-refresh-20260721`.

Validated:

- NanoPi capture remained 8 FPS with approximately 32-45 ms frame processing and approximately 92 ms dual-camera heavy detection; upload was the measured bottleneck at approximately 288-468 ms per accepted frame bundle.
- Frontend contract and VLA regressions: 5 passed. Both unified and historical platform Next production builds passed with only pre-existing warnings.
- Cloud `start-cloud-prod.sh` verified Web `:3001` and API `:8011` after restart. Authenticated browser QA remains unverified because the historical account returned `INVALID_CREDENTIALS`; no credential guessing was attempted.

Follow-up prepared:

- Added `upload_future_stalled()` watchdog to the NanoPi uploader; a blocked HTTP worker now exits after the configured 12-second limit so systemd can recover it instead of holding `upload_pending=True` forever. Local watchdog, vision, and calibration tests: 20 passed.
- NanoPi deployment of this watchdog is unverified because the hotspot entered multi-second SSH latency during scp; do not assume the board has the new file until its hash and PID are checked.

## 2026-07-21 - Post-calibration one-command readiness

Completed:

- Added `activate-session` and a NanoPi wrapper that finalize raw observations, solve, retain the candidate, atomically install only an accepted transform, and wait for live-context confirmation.
- Added a post-calibration preflight that distinguishes calibration readiness from the ordinary absence of a target/gripper in the current frame.
- Added a passive MuJoCo ROS visualizer plus Linux install and one-command shadow launch scripts.
- Added a no-network/no-ROS end-to-end QA from synthetic camera XYZ through robot XYZ, constrained IK, and Linux candidate validation.
- Added plural/singular cloud IK endpoint compatibility and a dashboard-evidence fallback that computes the constrained three-motor IK locally on Linux. A legacy generic six-axis cloud candidate is never treated as executable.

Validated:

- Vision, activation, preflight, offline, Linux-agent, and MuJoCo regression: 42 passed.
- Platform VLA target dispatch, closed-loop status, and sync regression: 42 passed.
- All three new shell scripts passed `bash -n` on NanoPi; the temporary Linux-script copies were removed afterward.
- Offline report: `candidate_ready`, six visual joints, three hardware joints, first scope `/sim/medical_arm/joint_trajectory`.
- NanoPi tools deployed and syntax checked; live preflight correctly returned exit `2` because the active calibration file does not yet exist, while `rehab-vla-vision.service` stayed active.
- Cloud dashboard returned 200; latest IK GET returned 404. Cloud SSH port is reachable, but the documented Ubuntu account rejected the local key, so no cloud files were changed.

Next:

- Collect the real poses and run the single activation command.
- When Linux becomes available, follow `docs/deploy/vla-closed-loop-rollout.md`; a cloud latest-IK upgrade is optional because the Linux fallback consumes existing calibrated dashboard evidence. Do not replace newer historical platform files.

## 2026-07-21 - Calibrated VLA target to MuJoCo/hardware staging

Completed:

- Connected accepted eye-to-hand matrices to the live NanoPi context; robot-frame target, gripper, and delta fields now fail closed on missing/rejected/mismatched calibration.
- Extended the platform stereo schema so robot-frame evidence is preserved instead of silently discarded.
- Added a calibration-provenance-bound three-motor IK candidate API and automatic L+V dispatch gate for `fetch_object`/`vision_servo`.
- Added a Linux execution agent that publishes MuJoCo shadow first and reuses the historical visual-zero slider protocol for optional supervised hardware ROS publication.
- Added a dedicated `medical_arm_visual_zero_3motor` MuJoCo profile/model/launch so the old demonstrated zero is not clamped by the generic six-axis limits.
- Added a 1 cm target-grid cache so unchanged 8 FPS vision frames reuse the same candidate rather than repeating the roughly 273 ms first IK solve.

Validated:

- Combined vision, calibration, Linux-agent, and MuJoCo-profile regression: 33 passed.
- Platform stereo, VLA closed-loop, IK dispatch, and sync tests: 42 passed.
- NanoPi process restarted as PID `9141`; service active, context freshness approximately 0.13 s, capture approximately 38.6 ms, and transform state correctly `waiting_calibration` while the accepted matrix file is absent.

Open:

- Complete the physical hand-eye samples and install an accepted `/home/pi/rehab_arm_calibration/base_from_camera.json`.
- Obtain the new Linux host IP, deploy the execution agent, and run a shadow-only candidate against the actual MuJoCo node/topic graph.
- Do not enable the two hardware flags until the shadow target, current M33 permission, joint mapping, and onsite arm state are all confirmed.

## 2026-07-21 - Three-motor visual-zero FK preparation

Completed:

- Recovered the authoritative visual-zero mapping from repository history commit `69450f71` instead of guessing motor signs or offsets.
- Added analytic FK for the current MuJoCo six-joint chain with only motors `4/5/6` active and the other joints frozen.
- Added `finalize-raw`, which preserves the raw session and writes FK-derived `base_link` gripper points to a separate session.
- Deployed the updated calibration utility to `/home/pi/rehab_arm_calibration/eye_to_hand_calibration.py`; the previous copy is retained as `.pre-fk-20260721`.
- Removed the cancelled platform/App migration worktree, branch, and temporary legacy remote without touching the dirty old platform or teammate BLE worktree.

Validated:

- Focused eye-to-hand tests: 8 passed; complete stereo/calibration algorithm selection: 18 passed.
- NanoPi `10.101.106.82` is online; `rehab-vla-vision.service` is active and the context file was fresh within 0.1 s during inspection.
- Live capture was approximately 44.8 ms while the parallel heavy detector evidence was approximately 102.6 ms.
- NanoPi import/CLI smoke test passed; zero hardware angles map to visual zero and produce model-base XYZ `[0.434872, -0.015363, 0.371270]` m.

Open:

- Runtime MuJoCo site cross-check was unavailable on the Windows host because its Python environment lacks `mujoco`; run the same comparison on the visualization host before accepting physical geometry.
- The migrated system-architecture test has a pre-existing root-path error and searched under `ros/docs`; 10 tests failed on missing files while 7 other selected guards passed.
- The live frame contained neither a plausible target nor a gripper in either eye, so the calibration session remains at zero observations.
- Acquire the first raw pose only when the gripper is fully visible and still in both cameras and motor `4/5/6` angles are authoritative.

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
