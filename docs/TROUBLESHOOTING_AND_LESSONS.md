# Troubleshooting And Lessons

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

