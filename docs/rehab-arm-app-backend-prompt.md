# Rehab Arm APP Backend Prompt

Updated: 2026-07-02

This prompt is for the AI or engineer implementing the mobile APP backend for the medical rehabilitation manipulator project. The backend must complement the existing cloud platform, NanoPi, M55, M33, and robot stack. It must not create a parallel robot-control authority.

## Current Mobile Delivery Note

The phone-facing APP is not a Python app. Python/FastAPI is only the backend service layer for user profiles, device binding, training plans, training records, EMG summaries, M55 intent summaries, audit logs, and platform sync.

Current frontend source of truth is the Stitch project:

```text
Stitch project: projects/9733571660387876930
Title: 灵动康复 ArmControl
```

The first runnable phone target is a mobile Web/PWA shell under:

```text
apps/web/public/rehab-arm-mobile/index.html
```

It embeds the Stitch-generated Chinese mobile screens for home, device connection, training library, AI planning, training execution, EMG monitoring, training report, and profile. This PWA can be opened on a phone browser and added to the home screen. A later Android APK can wrap the same mobile surface with Capacitor or a native Kotlin/Compose shell, but the visual flow should keep using Stitch as the source design.

## One-Sentence Boundary

The APP backend manages users, training plans, training records, AI training drafts, platform sync, and BLE-facing data contracts; it must never send CAN frames, motor current, motor torque, raw motor position/velocity, direct motor commands, or M33 safety overrides.

## System Context

Existing system roles:

- Cloud platform: VLA mode classification, vision evidence, MuJoCo/URDF digital twin, logs, review UI, competition demo control room.
- XiaoZhi / L: language input for chat, fetch-object mode, training mode, assistive EMG mode, diagnostics, and safety review.
- NanoPi: cameras, ROS2 bridge, edge perception, robot-side middleware.
- M55: EMG model inference, motion-intent prediction, confidence, muscle activation, fatigue hints.
- M33: BLE endpoint, training-plan receiver, safety gate, final execution authority.
- Mobile APP: user-facing training library, BLE near-field device connection, personal rehab profile, training records, AI training-plan draft review, low-risk confirmation UX.

Hard safety rules:

- The backend and APP do not directly control motors.
- The backend and APP do not send CAN frames.
- The backend and APP do not bypass M33.
- Training-plan sync means "M33 received a structured plan", not "motion is authorized".
- Any execution-capable workflow must show M33 state: waiting, accepted, rejected, stopped, or stale.

## Backend Implementation Prompt

Implement a backend for the rehabilitation-arm mobile APP.

The backend should support:

1. user profiles and roles;
2. device binding and M33 BLE identity records;
3. training-plan library;
4. training-plan versions and sync status;
5. training execution records;
6. EMG summary records from M55 or APP-side relay;
7. AI-generated training-plan drafts;
8. platform synchronization;
9. safety audit logs;
10. offline sync queues for mobile-first usage.

Do not implement direct robot control. Do not expose endpoints that can write motor torque, current, raw joint position, raw joint velocity, CAN messages, M33 override commands, or emergency-stop release commands.

Every API response related to training or device sync should include a `control_boundary` field such as:

```json
{
  "control_boundary": "training_plan_only_not_motor_command"
}
```

## Recommended Data Models

### UserProfile

```text
id
name
role: patient | therapist | family | engineer
affected_side
rehab_stage
medical_constraints
pain_baseline
created_at
updated_at
```

### DeviceBinding

```text
id
user_id
m33_device_id
ble_name
firmware_version
bound_at
last_seen_at
trust_status
platform_project_id
```

### TrainingPlan

```text
id
user_id
title
source: manual | ai_generated | therapist | imported
goal
target_joints
movement_type
sets
reps
duration_sec
target_angle_range
speed_level
assist_level
emg_policy
safety_constraints
status: draft | active | archived | rejected
version
created_at
updated_at
```

### TrainingPlanSync

```text
id
plan_id
device_id
sync_status: pending | sent | m33_accepted | m33_rejected | failed
m33_reason
synced_at
```

### TrainingSession

```text
id
user_id
plan_id
device_id
started_at
ended_at
status
completion_rate
interruption_count
avg_assist_level
max_assist_level
m33_reject_count
pain_after
user_note
```

### EmgSummary

```text
id
session_id
channel
muscle_name
rms_avg
peak
activation_avg
fatigue_index
contact_quality
created_at
```

### IntentInferenceSummary

```text
id
session_id
source: m55
predicted_action
confidence
topk
stability_score
created_at
```

### AiTrainingDraft

```text
id
user_id
input_text
context_snapshot
generated_plan
risk_notes
accepted_plan_id
created_at
```

### AuditLog

```text
id
actor
action
resource_type
resource_id
safety_level
detail
created_at
```

## Recommended API Surface

Use REST, tRPC, or the repo's existing API style. Keep route names explicit and shared by APP and platform where possible.

### User

```text
GET   /api/app/me
PATCH /api/app/me/profile
```

### Devices

```text
POST /api/app/devices/bind
GET  /api/app/devices
GET  /api/app/devices/:id/status
POST /api/app/devices/:id/diagnostic-upload
```

### Training Library

```text
GET   /api/app/training-plans
POST  /api/app/training-plans
GET   /api/app/training-plans/:id
PATCH /api/app/training-plans/:id
POST  /api/app/training-plans/:id/archive
POST  /api/app/training-plans/:id/sync-to-device
```

`sync-to-device` returns only sync state. It does not mean motion permission.

### Training Sessions

```text
POST  /api/app/training-sessions/start
PATCH /api/app/training-sessions/:id/progress
POST  /api/app/training-sessions/:id/finish
GET   /api/app/training-sessions
GET   /api/app/training-sessions/:id
```

### EMG

```text
POST /api/app/emg/summary
GET  /api/app/emg/latest
GET  /api/app/emg/history
```

### AI Training Drafts

```text
POST /api/app/ai-training-drafts/generate
GET  /api/app/ai-training-drafts/:id
POST /api/app/ai-training-drafts/:id/accept
```

### Platform Sync

```text
POST /api/app/platform/sync
GET  /api/app/platform/sync-status
```

## BLE Data Contract Prompt

Design the APP-to-M33 BLE contract around structured training and status messages.

Principles:

- BLE transmits training plans, device status, M33 safety decisions, training progress summaries, and diagnostics.
- BLE does not transmit raw motor commands.
- Each message has `schema_version`, `message_type`, `message_id`, `timestamp`, and `device_id`.
- Support ACK, error codes, and retry.
- M33 may reject any plan or session start request.

Message types:

```text
app_hello
device_status_request
training_plan_push
training_plan_ack
training_session_start_request
m33_safety_decision
training_progress_notify
training_pause_request
training_stop_request
diagnostic_snapshot_request
```

Example `training_plan_push`:

```json
{
  "schema_version": "rehab_app_ble_v1",
  "message_type": "training_plan_push",
  "message_id": "msg_001",
  "timestamp": 1783000000,
  "device_id": "m33-rehab-arm-alpha",
  "user_id": "user_001",
  "plan_id": "plan_001",
  "plan_version": 3,
  "movement_type": "elbow_flexion",
  "sets": 3,
  "reps": 10,
  "target_angle_range": {"min_deg": 15, "max_deg": 70},
  "speed_level": "slow",
  "assist_level": 0.3,
  "emg_policy": {
    "intent_source": "m55",
    "assist_when_confidence_above": 0.72
  },
  "safety_constraints": {
    "max_duration_sec": 900,
    "require_fresh_m33_heartbeat": true,
    "stop_on_pain_report": true
  },
  "control_boundary": "training_plan_only_not_motor_command"
}
```

Example `m33_safety_decision`:

```json
{
  "schema_version": "rehab_app_ble_v1",
  "message_type": "m33_safety_decision",
  "message_id": "msg_002",
  "timestamp": 1783000002,
  "device_id": "m33-rehab-arm-alpha",
  "related_message_id": "msg_001",
  "allowed": false,
  "reason": "joint_limit_or_estop_not_clear",
  "active_limits": ["elbow_angle_limit"],
  "emergency_stop": false,
  "control_boundary": "m33_final_safety_authority"
}
```

## AI Training Plan Generation Prompt

The backend may call an AI service to generate a training-plan draft.

The AI output must be a draft only:

- It may suggest training goals, sets, reps, duration, intensity, assist policy, and risk notes.
- It must include explanation and risk flags.
- It must not claim execution permission.
- It must not produce motor commands.
- The accepted draft becomes a `TrainingPlan`, then M33 decides whether it can be used.

Recommended AI input context:

```text
user profile
rehab stage
medical constraints
recent training sessions
pain and fatigue reports
EMG summaries
M55 intent stability
platform safety history
therapist notes
```

Recommended AI output:

```json
{
  "goal": "low intensity elbow flexion recovery",
  "movement_type": "elbow_flexion",
  "sets": 3,
  "reps": 8,
  "duration_sec": 600,
  "assist_level": 0.25,
  "emg_policy": "assist when biceps activation indicates flexion intent and confidence > 0.72",
  "risk_notes": ["stop if pain increases", "do not exceed configured elbow angle limit"],
  "explanation": "recent fatigue was mild, so use low intensity with slow movement",
  "control_boundary": "ai_draft_only_not_execution_permission"
}
```

## Platform Sync Contract

The APP backend should sync concise records to the cloud platform:

- training plans and versions;
- training session summaries;
- EMG summaries;
- M55 intent summaries;
- M33 accept/reject decisions;
- user notes and pain feedback;
- AI-generated draft metadata.

The platform should display these records as evidence and review data. The platform must not treat synced APP records as direct robot-control permission.

## Acceptance Checklist

- [ ] APP backend can create, edit, version, and archive training plans.
- [ ] APP backend can record M33 sync state including rejection reason.
- [ ] APP backend can store training session summaries.
- [ ] APP backend can store EMG and M55 inference summaries.
- [ ] AI training draft endpoint clearly marks output as draft only.
- [ ] All execution-adjacent APIs write audit logs.
- [ ] Every control-adjacent response includes `control_boundary`.
- [ ] No endpoint accepts CAN frames, raw motor commands, direct torque/current, or M33 overrides.
- [ ] Platform sync is evidence/review only.
