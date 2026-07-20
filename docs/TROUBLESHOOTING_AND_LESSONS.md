# Troubleshooting And Lessons

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
