# NanoPi RK3576 vision tools

This directory contains the latest NanoPi M5 VLA-V capture, inference, stereo
evidence, and upload utilities migrated from the former platform repository.
They are an edge evidence path only: none of these programs sends CAN frames,
publishes motor commands, or grants motion permission.

## Runtime pipeline

```text
two V4L2 cameras
  -> persistent C++ capture / OpenCV probe
  -> RK3576 RKNN INT8 inference (CPU ONNX fallback available)
  -> target and end-effector association
  -> calibrated point stereo or provisional dense stereo evidence
  -> asynchronous keyframe/context upload to the platform API
```

`nanopi-vla-cpp-upload-loop.py` is the orchestrator. Despite its historical
file name it contains the current Python control loop around the C++ capture
tools and RKNN runtime. Its output is tagged as evidence and must be transformed
and gated before any ROS trajectory candidate can be considered.

## Files

| File | Purpose |
| --- | --- |
| `nanopi-vla-cpp-upload-loop.py` | Multi-rate capture, RKNN/ONNX inference, stereo evidence, tracking, and asynchronous upload |
| `nanopi_vla_rknn_benchmark.py` | RKNN model latency and decode benchmark on RK3576 |
| `nanopi_stereo_natural_feature_calibration.py` | Provisional relative-pose estimate using natural features and a measured baseline |
| `nanopi_vla_capture_daemon.cpp` | Persistent dual-camera V4L2 capture process |
| `nanopi_vla_pixel_servo_probe_dnn.cpp` | OpenCV DNN detector probe and annotated evidence writer |
| `nanopi_vla_target_yolo_infer.py` | CPU ONNX target-inference helper retained as fallback |
| `eye_to_hand_calibration.py` | Fixed-camera eye-to-hand raw capture, rigid-transform solve, validation, and transform application |

## Three-motor eye-to-hand capture

The current calibration subset uses only motors `4/5/6`, mapped in this exact
order to `jian_zongxiang_joint`, `zhou_zongxiang_joint`, and
`jian_xuanzhuan_joint`. Motor 3 and both wrist joints remain frozen.

Initialize a session once, then capture each stopped pose. `capture-raw` records
the measured three-motor angles and a median of independent left/right gripper
XYZ samples. It does not require a robot-frame XYZ before forward kinematics is
available.

```bash
python3 eye_to_hand_calibration.py init \
  --output session_3motor.json \
  --stereo-calibration-id <active-stereo-calibration-id>

python3 eye_to_hand_calibration.py capture-raw \
  --session session_3motor.json \
  --context-json /home/pi/rehab_vla_frames/latest_platform_context.json \
  --pose-id P01 --split train \
  --joint-angles-deg 10.0,25.0,-5.0
```

The capture rejects reused target depth, single-eye estimates, unstable points,
duplicate frames, and stereo-calibration ID mismatches. Convert the recorded
angles through the visual-zero three-joint forward kinematics before running
the rigid transform solver; motor angles are never robot-frame XYZ by
themselves. The conversion writes a new session and preserves the raw file:

```bash
python3 eye_to_hand_calibration.py finalize-raw \
  --session session_3motor.json \
  --output session_3motor_with_fk.json

python3 eye_to_hand_calibration.py solve \
  --session session_3motor_with_fk.json \
  --output base_from_camera.json
```

After all train/validation poses are captured, the deployed NanoPi wrapper does
finalize, solve, fail-closed activation, and live-context verification in one
command:

```bash
/home/pi/rehab_arm_calibration/activate_hand_eye_and_preflight.sh \
  /home/pi/rehab_arm_calibration/session_3motor_20260721.json
```

A rejected candidate is retained as `base_from_camera.candidate.json` but never
overwrites `base_from_camera.json`. An accepted result is loaded by the running
8 FPS vision loop without a service restart.

The mapping follows visual-zero protocol commit `69450f71`: motor 4 maps to
`-0.675-m4`, motor 5 to `-1.12+m5`, and motor 6 to `m6` in the medical-arm
MuJoCo model. FK returns the gripper site relative to the model's `base` body,
not the floor/world offset. The result remains coordinate evidence only.

Natural-feature calibration and dense single-eye fallback are provisional
evidence. A printed calibration target and a verified camera-to-arm transform
remain required before using XYZ in a motion-planning candidate.

## Build and test

On the NanoPi, build the C++ helpers with the installed OpenCV 4 package:

```bash
g++ -std=c++17 -O3 nanopi_vla_capture_daemon.cpp \
  $(pkg-config --cflags --libs opencv4) -o nanopi_vla_capture_daemon
g++ -std=c++17 -O3 nanopi_vla_pixel_servo_probe_dnn.cpp \
  $(pkg-config --cflags --libs opencv4) -o nanopi_vla_pixel_servo_probe_dnn
```

Run the host-side algorithm tests from the repository root:

```bash
python -m pytest tools/nanopi/vision/test_nanopi_stereo_natural_feature_calibration.py \
  tools/nanopi/vision/test_nanopi_vla_stereo_dense_fallback.py \
  tools/nanopi/vision/test_eye_to_hand_calibration.py -q
```

RKNN execution itself requires the NanoPi RK3576 runtime and is not exercised
by the host tests.

## Provenance

The tracked Python pipeline is synchronized from
`wenjunyong666/ai-:feature/rehab-arm-rk3576-npu-20260712` at `b03ea772`.
The three C++/CPU helper sources were deployed working-tree snapshots from the
same project and had not been committed in that source repository; they are
recorded here explicitly so the new monorepo becomes their canonical baseline.
