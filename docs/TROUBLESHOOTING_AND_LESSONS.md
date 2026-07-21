# Troubleshooting And Lessons

## 2026-07-21 - Camera preview latency was dominated by upload and dashboard coupling

Symptom: NanoPi local vision advanced at 8 FPS, but the cloud control room looked closer to a slideshow and sometimes lagged by several seconds.

Evidence: local capture took roughly 32-45 ms, RKNN target inference roughly 14 ms per eye, and the complete heavy detector roughly 92 ms. Accepted upload bundles took roughly 288-468 ms and correctly skipped newer submissions while one upload was pending. The browser refreshed its full approximately 171 KB dashboard every 2 seconds, so image URLs changed at no more than 0.5 FPS even though latest keyframe files were only about 21-39 KB.

Fix: keep the expensive dashboard poll at 2 seconds, but while the Stitch `vision` module is visible refresh only the left/right latest-file image URLs every 350 ms. Update the iframe image nodes directly instead of changing React state and rerendering the entire control room. Stop the timer when the tab is hidden or the user leaves the vision module.

Deployment lesson: a long interactive SSH build was disconnected before publishing. Run the cloud build with an independent log/status artifact, confirm the complete route manifest, and only then call `RESTART=1 scripts/start-cloud-prod.sh`. Do not infer success from an uploaded source file or a still-healthy old service.

Status: deployed; cloud services healthy. Final authenticated visual/network QA is pending a valid account credential.

## 2026-07-21 - NanoPi upload worker can remain pending indefinitely

Symptom: the capture loop continued advancing from frame `12113` to `19754`, but there were no `upload_done` records for more than 90 seconds. The context repeatedly reported `upload_pending=True` and `upload_skipped=True`, while the cloud latest image stayed unchanged until a later upload completed.

Root cause: the single `ThreadPoolExecutor(max_workers=1)` upload future combines two keyframe POSTs and one stereo-context POST. A long network/server read can occupy the worker indefinitely; the capture loop intentionally keeps observing but cannot submit another upload.

Fix prepared: `tools/nanopi/vision/nanopi-vla-cpp-upload-loop.py` records the upload start monotonic time and exits with status `3` after `REHAB_UPLOAD_STALL_TIMEOUT_S` (default 12 seconds). The service manager can then restart a clean worker; this preserves latest-only behavior and avoids unbounded frame queues.

Status: local tests pass; NanoPi file copy/restart is pending because the current hotspot SSH path reached 262-2365 ms ping and timed out during scp.

## 2026-07-21 - Activation and cloud version must both be fail-closed

Calibration rule: write the solved result to a candidate artifact first. Only `calibration_state=accepted` may atomically replace `base_from_camera.json`; rejected validation must leave any known-good active file unchanged.

Runtime rule: the vision service reloads the calibration during heavy context generation, so successful activation does not require a restart. Verify live calibration and stereo IDs instead of restarting a working 8 FPS service.

Cloud lesson: the live platform source is newer than the unified migration snapshot and already uses plural `/ik-candidates` plus shadow-step features. Whole-file deployment from the unified tree would regress those features. Patch against the live checkout, or use the Linux agent's plural/singular/dashboard compatibility until authorized deployment is possible.

Status: NanoPi and offline contracts are ready; cloud latest GET remains undeployed and the current local SSH key is unauthorized.

## 2026-07-21 - Reuse the visual-zero slider path for VLA execution

Symptom: the platform had camera XYZ and a generic six-DOF IK scaffold, but NanoPi forced robot-frame fields to `None`, the API schema discarded extra transform fields, and the generic IK could move joints that are not installed.

Fix: load only an accepted stereo-bound eye-to-hand matrix, preserve robot-frame evidence in the API, solve the constrained motor `4/5/6` visual-zero model, and stage the result through `/sim/medical_arm/joint_trajectory`. The optional final ROS publication reuses commit `69450f71` and `/arm_controller/joint_trajectory` instead of creating a second hardware path.

Performance lesson: the initial three-motor multi-seed IK took roughly 273 ms on the Windows host. Cache candidates by calibration ID and a 1 cm target grid so 8 FPS evidence refresh does not become 8 FPS IK recomputation.

Deployment lesson: replacing the NanoPi Python file does not update the running process. The first restart attempt was blocked by sudo, leaving old PID `993` and old `transform_state=waiting`; after an authenticated service-only restart, PID `9141` emitted the new `waiting_calibration` state. Verify both PID and live context fields after deployment.

MuJoCo lesson: the generic ROS backend clamps to the original six-axis ranges, while the demonstrated visual zero has shoulder/elbow/wrist values outside those ranges. The historical slider viewer worked because it assigned qpos directly. Keep the generic profile unchanged and launch `medical_arm_visual_zero_3motor_shadow.launch.py` for this chain; otherwise the execution agent will wait forever for a shadow pose the backend cannot represent.

## 2026-07-21 - Recover visual-zero evidence before deriving hand-eye robot points

Symptom: the active tree had a raw three-motor capture path, but the temporary calibration YAML still marked motor `4/5/6` zero and direction as TODO. Treating raw angles directly as model qpos would produce plausible but wrong `base_link` points.

Fix: recover repository history commit `69450f71`, which records the demonstrated hardware-slider/visual-zero mapping. Keep raw observations immutable, convert degrees to the mapped visual qpos in `finalize-raw`, and derive the gripper site relative to the MuJoCo `base` body rather than including the model's floor/world height.

Reusable rule: a rendered zero pose, a motor output zero, and a robot base frame are three different concepts. Preserve the raw joint sample and attach the exact model/mapping provenance to every derived robot point.

Status: analytic tests pass; runtime comparison against MuJoCo and physical-link validation remain required before accepting the transform.

Test note: `test_system_architecture_contract.py` currently derives `REPO_ROOT` as the monorepo `ros` directory after migration, so it reports missing `ros/docs/*` files. Do not interpret those path failures as FK or safety-contract regressions; repair that test root separately.

## 2026-07-21 - Hand-eye samples require independent gripper stereo depth

Symptom: the old context could produce an end-effector camera point by projecting the left gripper pixel with the target bottle depth. This looks numerically complete but is not a valid hand-eye correspondence.

Fix: infer the gripper independently in both eyes, require a valid rectified stereo match, aggregate distinct stable frames, and reject the sample otherwise. Record motor `4/5/6` angles separately; apply validated three-joint FK before solving `base_from_camera`.

Performance lesson: do not create two concurrent RKNNLite runtimes for the same gripper model on RK3576. The first attempt raised load and made SSH/network response sluggish. Share one runtime and serialize left/right gripper inference; the live heavy pipeline recovered to roughly 74 ms.

Status: capture tooling and runtime are deployed; first real pose is waiting for a fully visible, stationary gripper tip in both cameras and authoritative three-motor angles.

## 2026-07-21 - Do not force a Wi-Fi switch before the preferred hotspot is visible

Symptom: NanoPi is reachable through the current fallback hotspot, while the new preferred SSID is configured but absent from both the PC and board scan results.

Fix: create the preferred NetworkManager profile first, enable autoconnect, assign it a higher priority, and retain the current profile at a lower priority. Do not force `nmcli connection up` while the target hotspot is absent; doing so can drop the only management path without proving the new path.

Reusable rule: distinguish “profile persisted” from “hotspot currently visible and active.” Verify `connection.autoconnect`, `connection.autoconnect-priority`, and the active profile separately. Never solve this condition by changing the kernel or Wi-Fi driver when the existing interface is already working.

## 2026-07-20 - RK3576 NPU module must match the running kernel

Symptom: the default `rknpu.ko` may fail to load with a `module_layout` modversion
or symbol mismatch even though RKNN user-space packages are installed.

Known cause: the previously validated NanoPi ran a custom `6.1.141` kernel and
used an already existing matching module under the corresponding
`/lib/modules/6.1.141.can-new` tree. A module built for another kernel tree is
not interchangeable.

Rule: do not replace or rebuild the kernel to repair this project path. First
record `uname -r`, inspect the existing module tree, and compare the deployed
service configuration. Load only a module already proven compatible with the
active kernel. Repository synchronization never writes kernel or module files.

Status: historical live evidence reported NPU driver v0.9.8 and active vision
service, but the device was offline during the 2026-07-20 monorepo sync.

## 2026-07-20 - Keep capture, inference, and upload ownership separate

Symptom: a synchronous camera/inference/upload loop exhibits long frame stalls
when cloud upload or heavy stereo processing is slow.

Fix used by the synchronized pipeline: persistent C++ camera capture, cached
RKNN sessions, bounded worker executors, atomic evidence files, and one
asynchronous upload worker. New frames replace stale display evidence instead
of building an unbounded image queue.

Reusable rule: visual throughput optimization must not create a second motion
authority. Detection and depth remain evidence; ROS and M33 gates remain intact.
