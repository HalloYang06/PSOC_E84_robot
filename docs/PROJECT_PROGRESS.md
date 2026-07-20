# Project Progress

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

