# Medical Rehab Arm NanoPi / VLA / MuJoCo Integration

Updated: 2026-06-17

This document describes how NanoPi uploads camera, EMG/model outputs, VLA action candidates, and MuJoCo simulation evidence into the existing AI collaboration platform. It does not redefine the robot-side protocol. The platform remains a relay, evidence, and review surface.

## Safety Boundary

- Real motion still goes through `JointTrajectory -> NanoPi -> M33 -> motor`.
- M33 is the final safety authority.
- The platform, browser, LLM, VLA, M55, MuJoCo, and App must not send CAN frames, motor current, motor torque, raw motor position/velocity, direct motor commands, or M33 safety overrides.
- VLA output accepted by the platform is only high-level intent or `dry_run_joint_trajectory_candidate`.
- A MuJoCo pass is evidence, not real motion permission.

## Identity

Default device identity for the current bench:

```text
project_id = fd6a55ed-a63c-44b3-b123-96fb3c154966
device_id  = nanopi-m5
robot_id   = rehab-arm-alpha
api_base   = http://106.55.62.122:8011
```

Edge devices should use a scoped `rehab-relay.v1...` token from the Model Relay Lab. Vendor model API keys stay on the server.

## 1. Camera Keyframes From NanoPi

Use low-frequency keyframes for platform display and VLA-V context. This is perception evidence only.

Endpoint:

```text
POST /api/rehab-arm/v1/devices/{device_id}/camera/keyframes
Content-Type: multipart/form-data
```

Fields:

```text
robot_id          required, e.g. rehab-arm-alpha
project_id        required for account/project isolation
camera_id         required, e.g. front_rgb
frame_ts_unix     required unix seconds
image_format      jpg | jpeg | png | webp
width             pixels
height            pixels
sha256            optional; checked when present
detection_summary optional model/perception summary
scene_summary     optional human-readable scene summary
vla_context       optional V-context text for VLA
file              image bytes
```

Example:

```bash
curl -X POST "$API/api/rehab-arm/v1/devices/nanopi-m5/camera/keyframes" \
  -F robot_id=rehab-arm-alpha \
  -F project_id=fd6a55ed-a63c-44b3-b123-96fb3c154966 \
  -F camera_id=front_rgb \
  -F frame_ts_unix="$(date +%s)" \
  -F image_format=jpg \
  -F width=1280 \
  -F height=720 \
  -F scene_summary="patient seated, arm visible, therapist nearby" \
  -F detection_summary="shoulder/elbow visible; workspace clear" \
  -F vla_context="Use image as V input only; not motion permission." \
  -F file=@frame.jpg
```

Future streaming can use `camera_stream_offer_v1`, but the platform should still treat camera streams as perception display and VLA input, not control.

## 1.1 Two RGB Cameras + Pretrained YOLO First Pass

Use two RGB cameras as a stereo pair when no depth camera is available. Run pretrained YOLO locally on the edge, estimate a coarse target depth, and upload one stereo vision context record.

Endpoint:

```text
POST /api/rehab-arm/v1/devices/{device_id}/vision/stereo-context
Content-Type: application/json
```

Recommended payload:

```json
{
  "schema_version": "stereo_rgb_yolo_context_v1",
  "robot_id": "rehab-arm-alpha",
  "device_id": "nanopi-m5",
  "project_id": "fd6a55ed-a63c-44b3-b123-96fb3c154966",
  "frame_ts_unix": 1781079000.0,
  "left_camera_id": "left_rgb",
  "right_camera_id": "right_rgb",
  "stereo_calibration_id": "bench_calib_001",
  "baseline_m": 0.08,
  "image_pair_ref": {
    "left_image_url": "/api/rehab-arm/v1/devices/nanopi-m5/camera/keyframes/latest/file",
    "right_image_url": "/api/rehab-arm/v1/devices/nanopi-m5/camera/keyframes/latest/file"
  },
  "detections": [
    {"label": "cup", "confidence": 0.91, "bbox": [120, 88, 184, 170]},
    {"label": "hand", "confidence": 0.87, "bbox": [212, 96, 264, 176]}
  ],
  "target_object": {"label": "cup", "confidence": 0.91},
  "estimated_depth_m": 0.72,
  "target_3d_camera_frame": {"x": 0.12, "y": -0.03, "z": 0.72},
  "scene_summary": "cup on table, hand visible, workspace clear",
  "vla_context": "two RGB cameras provide approximate depth only; operator must verify before motion",
  "confidence": 0.91
}
```

The platform stores this as perception evidence only and prefers it over single keyframes when building `vla_vision_context`.

Practical notes:

- Treat the stereo depth as approximate, not clinical-grade depth.
- Keep calibration and disparity logic in the edge script, not the motion controller.
- Use YOLO only for object detection and coarse target selection.
- The platform still outputs high-level task intent, not joint trajectories or CAN frames.

## 2. EMG / Sensor / Muscle Small-Model Output From NanoPi

Use `sensor_state` for raw-ish EMG summaries and local model results. The UI maps muscle effort and fatigue from this payload.

Endpoint:

```text
POST /api/rehab-arm/v1/devices/{device_id}/sensor-state
Content-Type: application/json
```

Recommended payload:

```json
{
  "robot_id": "rehab-arm-alpha",
  "device_id": "nanopi-m5",
  "project_id": "fd6a55ed-a63c-44b3-b123-96fb3c154966",
  "ts_unix": 1781079000.0,
  "source": "nanopi_m55_emg_bridge",
  "emg": {
    "schema_version": "emg_summary_v1",
    "channels": [
      {"channel": "emg_1", "muscle": "deltoid", "rms": 0.31, "activation": 0.62, "fresh": true},
      {"channel": "emg_2", "muscle": "biceps", "rms": 0.22, "activation": 0.44, "fresh": true},
      {"channel": "emg_3", "muscle": "forearm_flexor", "rms": 0.18, "activation": 0.36, "fresh": true},
      {"channel": "emg_4", "muscle": "trapezius", "rms": 0.12, "activation": 0.24, "fresh": true}
    ],
    "control_boundary": "sensor_summary_only_not_motion_permission"
  },
  "fatigue_score": 0.28,
  "intent_prediction": {
    "schema_version": "rehab_intent_prediction_v1",
    "label": "assist_slow_raise_arm",
    "confidence": 0.78,
    "participates_in_vla_l": false,
    "control_boundary": "local_model_suggestion_only_not_motion_permission"
  },
  "model_outputs": {
    "schema_version": "muscle_model_outputs_v1",
    "muscle_effort": {
      "shoulder": 0.62,
      "upper_arm": 0.44,
      "forearm": 0.36,
      "neck_shoulder": 0.24
    },
    "fatigue_state": "low",
    "recommendation": "continue observation; do not auto-control"
  }
}
```

Any missing/stale/faulty sensor channel is alarm-only. The platform must not auto-compensate motor control from EMG.

## 3. Voice / Language Into VLA-L

M55 XiaoZhi WebSocket and HTTP model relay both classify language through the server model relay.

### XiaoZhi WebSocket Contract

The long-term target is the official XiaoZhi WebSocket contract, but the current Infineon M55/M33 onsite image is stable on a v1/raw-PCM path. The platform therefore defaults new connections without a `Protocol-Version` header to `Protocol-Version = 1` and `audio_params.format = pcm_s16le` so the board can complete ASR/LLM/TTS bring-up before the M55 Opus path is re-enabled.

Current M55 onsite headers:

```text
Authorization: Bearer rehab-relay.v1...
Device-Id: nanopi-m5
Client-Id: <stable client id>
```

Current M55 onsite hello:

```json
{
  "type": "hello",
  "version": 1,
  "transport": "websocket",
  "audio_params": {
    "format": "pcm_s16le",
    "sample_rate": 16000,
    "channels": 1,
    "bits_per_sample": 16,
    "frame_duration": 60
  }
}
```

Official v3/Opus clients can still opt in explicitly:

```json
{
  "type": "hello",
  "version": 3,
  "transport": "websocket",
  "features": {"mcp": true},
  "audio_params": {
    "format": "opus",
    "sample_rate": 16000,
    "channels": 1,
    "frame_duration": 60
  }
}
```

For `Protocol-Version: 3`, binary audio frames use `BinaryProtocol3`:

```text
uint8_t  type
uint8_t  reserved
uint16_t payload_size   # big-endian
uint8_t  payload[]      # official payload is Opus
```

The board may temporarily send `audio_params.format = "pcm_s16le"` while the M55 Opus encoder is not ready. The platform records that as `compatibility_mode = debug_pcm_s16le_not_official_xiaozhi_audio`; it is only for link/ASR debugging and must not be documented as the official device protocol.

Current server behavior:

- no `Protocol-Version` header: default to `version=1`, raw binary audio, 16 kHz mono S16LE PCM, 60 ms frames.
- `format=opus`: accepted as the official XiaoZhi audio path. The server preserves WebSocket packet boundaries, decodes each Opus frame to 16 kHz mono S16LE PCM with `opuslib`/system `libopus`, then sends the decoded WAV to the configured ASR provider. If the decoder runtime is missing or a packet cannot be decoded, STT returns an explicit `opus_decoder_unavailable:*` or `opus_decode_failed:*` error instead of silently pretending to understand audio.
- `format=pcm_s16le`: accepted as the current onsite M55 compatibility branch. The server wraps 16 kHz mono PCM S16LE into WAV and sends it to the configured ASR provider.
- `hello.version` must match `Protocol-Version` when the header is present.
- TTS provider output must decode to audible 16 kHz mono S16LE PCM. Extremely short PCM output, such as the observed 640-byte/20 ms downlink, is recorded as `tts_audio_too_short` and is not forwarded as fake speech.
- `listen start`, `listen detect`, and `listen stop` are recorded in the command-center input/output stream.

The response contains:

```json
{
  "classification": {"type": "daily_chat"},
  "vla_language_gate": {
    "participates_in_vla_l": false,
    "route": "daily_chat_only"
  }
}
```

or:

```json
{
  "classification": {"type": "vla_command"},
  "vla_language_gate": {
    "participates_in_vla_l": true,
    "route": "vla_l_input"
  }
}
```

Only `vla_command` enters the VLA L input. Daily chat stays chat-only.

## 4. VLA-A Into The Main Robot Line

VLA-A enters the platform as a high-level task request. It is not a real motion command.

Project-scoped endpoint:

```text
POST /api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/vla/task-requests
Authorization: Bearer rehab-relay.v1...
Content-Type: application/json
```

Payload:

```json
{
  "schema_version": "vla_task_request_v1",
  "robot_id": "rehab-arm-alpha",
  "device_id": "nanopi-m5",
  "project_id": "fd6a55ed-a63c-44b3-b123-96fb3c154966",
  "session_id": "session_20260613_001",
  "language_goal": "Patient requested slow assisted arm raise. Generate a MuJoCo dry-run candidate only.",
  "context_refs": {
    "vla_language_context_id": "lang_ctx_xxx",
    "vla_vision_context_id": "vision_ctx_xxx",
    "sensor_state_ref": "latest",
    "robot_render_state_ref": "latest"
  },
  "allowed_outputs": ["high_level_task", "dry_run_joint_trajectory_candidate"],
  "forbidden_outputs": [
    "can_frame",
    "motor_current",
    "motor_torque",
    "raw_motor_position",
    "raw_motor_velocity",
    "m33_safety_override"
  ],
  "control_boundary": "vla_planning_request_only_not_motion_permission"
}
```

The platform returns `vla_plan_candidate_v1` with:

- dry-run candidate metadata
- `requires`: `mujoco_dry_run_passed`, `m33_motion_allowed_true`, `human_confirmation`
- `control_boundary = vla_candidate_only_not_motion_permission`

The action path is:

```text
VLA candidate
  -> platform audit record
  -> MuJoCo dry-run on simulation host
  -> simulation_readiness/report upload
  -> human review
  -> NanoPi ROS layer may prepare JointTrajectory
  -> M33 final safety gate
  -> motors
```

## 5. MuJoCo Simulation Evidence Back To Platform

MuJoCo does not authorize real motion. It uploads evidence.

Endpoint:

```text
POST /api/rehab-arm/v1/devices/{device_id}/simulation-readiness
Content-Type: application/json
```

Payload:

```json
{
  "robot_id": "rehab-arm-alpha",
  "device_id": "nanopi-m5",
  "project_id": "fd6a55ed-a63c-44b3-b123-96fb3c154966",
  "report": {
    "schema_version": "mujoco_dry_run_report_v1",
    "ok": true,
    "readiness": "dry_run_passed",
    "vla_plan_id": "vla_plan_1781079000000",
    "scenario_id": "slow_raise_arm_001",
    "duration_sec": 6.0,
    "max_joint_limit_margin_rad": 0.18,
    "collision_free": true,
    "estimated_peak_torque": {
      "jian_hengxiang_joint": 0.42,
      "jian_zongxiang_joint": 0.38
    },
    "warnings": [],
    "artifacts": {
      "video_url": "",
      "trace_url": "",
      "metrics_url": ""
    },
    "control_boundary": "simulation_evidence_only_not_motion_permission"
  }
}
```

## 6. Training VLA

Recommended first training path:

1. Collect synchronized data through NanoPi:
   - camera keyframes or video samples
   - XiaoZhi/voice transcript and language gate
   - EMG/sensor summaries
   - robot render state and joint telemetry
   - safety state and wiring health
   - human labels: intended rehab action, pain/fatigue feedback, accept/reject

2. Curate dataset:
   - split by patient/session/device
   - remove samples with missing safety state or stale joints
   - mark daily chat as negative L samples
   - mark VLA commands as positive L samples
   - keep all outputs high-level; do not train on CAN/current/torque commands

3. Train in stages:
   - L classifier: daily chat vs VLA command
   - V/L context encoder: camera scene + language + EMG summary
   - A candidate model: high-level task and dry-run candidate proposal
   - Safety/rejection head: reject when wiring/safety/data freshness is poor

4. Evaluate:
   - language gate accuracy
   - false positive VLA command rate
   - dry-run pass rate in MuJoCo
   - safety rejection recall
   - no low-level forbidden fields in output

5. Export model:
   - register model version in platform notes/evidence
   - run offline replay against held-out sessions
   - run MuJoCo scenarios
   - only then connect model inference to `vla/task-requests`

## 7. Training To MuJoCo Flow

```text
NanoPi uploads dataset
  -> platform indexes sessions
  -> human/NPC labels V/L/A samples
  -> train VLA model on GPU workstation
  -> model emits vla_task_request_v1
  -> platform records vla_plan_candidate_v1
  -> MuJoCo host consumes candidate and uploads simulation_readiness
  -> operator reviews evidence
  -> real robot path remains JointTrajectory -> NanoPi -> M33 -> motor
```

The platform should expose the model and simulation results as evidence. It should not become the real-time controller.

## 8. Progress Notes

### 2026-06-17 - XiaoZhi UI State Contract Added

- Completed: the platform XiaoZhi session snapshot now exposes `ui_state` and `last_error` so the front end/LVGL can render `listening`, `wake_detected`, `thinking`, `speaking`, `idle`, and `error` without guessing from the last event type.
- Completed: `ui_state` is driven by the merged `xiaozhi_session_v1` snapshot, not by a single TTS bookkeeping record.
- Validation: XiaoZhi-specific backend tests still pass after the state contract update.
- Boundary: this only improves observability and user feedback; it does not change the official XiaoZhi audio path or any motion authority.

### 2026-06-17 - Stereo RGB + Pretrained YOLO Framework Added

- Completed: added a `stereo_rgb_yolo_context_v1` perception-only contract for two RGB cameras and pretrained YOLO output.
- Completed: the platform now stores `stereo_vision_context` as latest device telemetry and prefers it when building `vla_vision_context`.
- Completed: model relay now surfaces stereo target label, approximate depth, and image-pair references as high-level vision context only.
- Validation: backend test coverage added for stereo context upload, dashboard visibility, and model relay preference.
- Boundary: two RGB cameras are acceptable for the first runnable pass, but depth remains approximate and must not be treated as motion permission.

### 2026-06-17 - XiaoZhi WebSocket Session State Stabilized

- Completed: the platform now records a merged `xiaozhi_session_v1` device status instead of letting the last TTS bookkeeping event overwrite the voice/listen/reply state.
- Completed: the session status preserves audio byte count, audio duration, `official_audio_path`, `compatibility_mode`, ASR state, LLM entry state, and TTS provider status for the latest XiaoZhi interaction.
- Validation: targeted backend tests passed for scoped relay-token WebSocket access, official Opus v3 handling, PCM compatibility frame parsing, ASR-not-configured surfacing, and missing TTS configuration surfacing.
- Boundary: Opus remains the official XiaoZhi audio path. `pcm_s16le` remains a debug compatibility path for current M55 bring-up and is recorded as `debug_pcm_s16le_not_official_xiaozhi_audio`.
- Safety: this path only produces speech/LLM/VLA-language context and operator-facing replies. It still does not produce CAN frames, motor current/torque, direct motor commands, or M33 safety overrides.

### 2026-06-23 - XiaoZhi M55 v1 PCM Platform Default

- Completed: platform XiaoZhi WebSocket now defaults clients without `Protocol-Version` to `version=1` and `pcm_s16le`, matching the current stable Infineon M55/M33 image instead of forcing v3/Opus during onsite bring-up.
- Completed: `hello` without `audio_params` preserves the negotiated default instead of silently falling back to Opus.
- Completed: TTS PCM shorter than the audible threshold is reported as `tts_audio_too_short` and not forwarded to the board, preventing 640-byte noise bursts from being treated as successful human speech.
- Completed: official v3/Opus audio now decodes server-side before ASR when Python `opuslib` and system `libopus` are available. The WebSocket router passes the original Opus packet list into ASR so decoder frame boundaries match the XiaoZhi protocol.
- Validation: `python -m pytest apps/api/tests/test_rehab_arm_sync.py -k "xiaozhi"` passed, including v1/raw-PCM default, explicit v3/Opus compatibility, Opus-to-ASR decode, stale ASR clearing, and short-TTS rejection.
- Boundary: official v3/Opus remains available when a client sends `Protocol-Version: 3` and Opus audio params explicitly; the default is changed only to match the current deployed board path. Cloud deployment must install both `opuslib==3.0.1` and the OS `libopus` runtime.
