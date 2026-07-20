# NanoPi RK3576 vision sync - 2026-07-20

## Scope

This sync promotes only the latest NanoPi VLA-V edge implementation into the
canonical monorepo. It does not import unrelated platform, App, XiaoZhi/L, BLE,
M33/M55, CAN, MuJoCo, or real-motion changes from the former repository.

Source repository: `https://github.com/wenjunyong666/ai-`

Source branch: `feature/rehab-arm-rk3576-npu-20260712`

Latest committed source: `b03ea772` (`Stabilize live NanoPi stereo throughput`)

Included committed sequence:

- `ab304360` - Accelerate NanoPi vision with RK3576 NPU
- `0f008006` - Harden stereo association evidence
- `bd6ff25a` - Add provisional dense stereo depth fallback
- `95dc7aa4` - Accelerate provisional stereo depth
- `b03ea772` - Stabilize live NanoPi stereo throughput

The synchronized files live in `tools/nanopi/vision`. Three helper sources
(`nanopi_vla_capture_daemon.cpp`, `nanopi_vla_pixel_servo_probe_dnn.cpp`, and
`nanopi_vla_target_yolo_infer.py`) existed as deployed, uncommitted working-tree
files in the source project. Their first canonical tracked baseline is this
monorepo sync.

## Verified source evidence

The former project records the live RK3576 pipeline at approximately 8-10 FPS,
with persistent RKNN INT8 target/gripper sessions, inference commonly around
10-24 ms, and asynchronous uploads commonly around 35-80 ms. Those figures are
historical hardware evidence, not a fresh validation on this checkout.

The active device used an existing kernel-compatible `rknpu.ko` loaded by
`rehab-rknpu-load.service` before `rehab-vla-vision.service`. This sync does not
include, replace, or modify a kernel or kernel module. The service unit files
were not available as tracked source and must be recovered from the NanoPi
before treating deployment reconstruction as complete.

## Boundary

The tools output annotated frames, detections, confidence, association quality,
and provisional stereo depth. They do not output motion permission and do not
send CAN or raw motor commands. Camera-frame XYZ must still pass calibration,
camera-to-arm transformation, ROS trajectory validation, the NanoPi gate, and
M33 final safety arbitration.

