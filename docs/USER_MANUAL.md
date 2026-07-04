# User Manual

## Stereo RGB + YOLO First Run

1. Capture left/right RGB frames on the edge device.
2. Run pretrained YOLO locally and choose one target object.
3. Estimate a coarse target depth from the stereo pair.
4. POST the result to:

```text
/api/rehab-arm/v1/devices/{device_id}/vision/stereo-context
```

5. Keep `control_boundary` set to `stereo_vision_context_only_not_motion_permission`.
6. Use the returned `vla_vision_context` only as high-level input for the main line.

### Optional end-effector ONNX detector

The NanoPi read-only collector can attach the user-trained `end_effector` / `gripper_tip` YOLOv8 ONNX detector to the stereo evidence path. This does not grant motion permission; it only adds detector evidence to `stereo_vision_context`.

```powershell
python scripts\nanopi-rehab-arm-collect-and-upload.py `
  --project-id e201f41c-25a6-46e1-baf8-be6dcb83284c `
  --device-id nanopi-m5 `
  --robot-id rehab-arm-alpha `
  --capture-stereo-keyframes `
  --left-camera-index 0 `
  --right-camera-index 1 `
  --left-flip hv `
  --right-flip hv `
  --flip-applied-before-detection `
  --end-effector-onnx D:\vla_dataset\20260627_213112\runs\end_effector_v1_cpu_416_e10\weights\best.onnx
```

Expected evidence fields:

- `stereo_context.detections.left/right[]` contains real OpenCV DNN / YOLO outputs.
- `stereo_context.end_effector_object` is the highest-confidence `end_effector`.
- `stereo_context.gripper_tip_object` is the highest-confidence `gripper_tip`.
- `control_boundary` remains `stereo_vision_context_only_not_motion_permission`.

## Rehab Arm 3D Twin URDF / IK Check

Cloud control room:

```text
http://106.55.62.122:3001/projects/e201f41c-25a6-46e1-baf8-be6dcb83284c/rehab-arm-control
```

1. Open `3D / 孪生`.
2. In `IK DRY-RUN EVIDENCE`, type candidate `robot_frame` coordinates. The typed values should stay in the input boxes while the page refreshes.
3. Use the Stitch `导入 URDF / ZIP 模型包` area to upload `.urdf`, `.xml`, or `.zip`.
4. A successful import must update both places: the Stitch label shows `当前模型: <file>` and the real Three.js portal `#codex-twin-runtime-stage` shows `已导入 <file>` plus parsed joint evidence. A label-only change is not enough.
5. This page is still evidence/dry-run only. It must not publish CAN frames, raw motor setpoints, M33 overrides, or real motion permission.

## Rehab Arm Phone PWA Preview

Cloud phone preview:

```text
http://106.55.62.122:3001/rehab-arm-mobile/index.html
```

1. Start the static preview from `apps/web/public`:

```text
python -m http.server 4177 --bind 127.0.0.1
```

2. Open `http://127.0.0.1:4177/rehab-arm-mobile/index.html` on desktop or phone browser.
3. Optional backend connection: set `localStorage.rehabArmMobileApiBase` to the API origin that serves `/api/rehab-arm/app/v1`.
4. Keep the safety boundary visible: App sync submits structured training data for M33 review only. It is not motion permission and must not release emergency stop.
5. On Android Chrome, use "Add to Home screen" from the browser menu. The PWA includes standalone display metadata and maskable PNG icons for install preview.

## Rehab Arm App Backend Closed Loop

Mobile App backend namespace:

```text
/api/rehab-arm/app/v1
```

Core closed-loop flow:

1. `PATCH /me/profile` creates or updates the patient profile.
2. `POST /devices/bind` binds an M33 BLE device identity.
   - Rebinding a device with `trust_status=revoked` keeps it visible for audit/diagnostics but blocks plan sync, BLE messages, M33 status updates, and training starts with `DEVICE_REVOKED`.
3. `POST /training-plans` creates a plan, or `POST /ai-training-drafts/generate` creates an AI draft that can be accepted through `/ai-training-drafts/{draft_id}/accept`.
4. `POST /training-plans/{plan_id}/sync-to-device` submits the current plan version for M33 review.
5. `POST /devices/{device_id}/m33-status` records the M33 decision. `m33_accepted` is required before a session record can start.
6. `POST /training-sessions/start` starts only if the selected plan/device has current-version `m33_accepted` and the selected device has no active session. Otherwise it returns `M33_ACCEPTANCE_REQUIRED` or `ACTIVE_TRAINING_SESSION_EXISTS`.
7. `PATCH /training-sessions/{session_id}/progress`, `POST /emg/summary`, `POST /intent/summary`, and `POST /training-sessions/{session_id}/finish` store evidence and records only. Once a session is `finished`, progress and finish updates return `TRAINING_SESSION_NOT_ACTIVE`.
8. `POST /training-sessions/{session_id}/report` generates the post-session training report only after the session is finished. Repeating the request returns the existing report, and late EMG/intent uploads for that session return `TRAINING_REPORT_ALREADY_GENERATED`.
9. `POST /training-reports/{report_id}/reviews` records human review and next-step intent without creating motion permission.
10. `POST /training-reports/{report_id}/draft-next-plan` creates the next AI draft from report/review evidence only. Accepting that draft creates a normal plan, and the plan still needs current-version M33 acceptance before the next session can start.

Useful reads:

```text
GET /me
GET /devices/{device_id}/status
GET /devices/{device_id}/diagnostics
GET /devices/{device_id}/ble/messages
GET /training-plans/{plan_id}
GET /training-plans/{plan_id}/readiness?device_id=...
GET /training-plans/{plan_id}/start-guide?device_id=...
GET /training-plans/{plan_id}/constraint-reviews
GET /training-preflight
GET /training-sessions
GET /training-sessions/{session_id}
GET /training-sessions/{session_id}/safety-events
GET /training-sessions/{session_id}/report
GET /training-reports
GET /training-reports/{report_id}
GET /training-reports/{report_id}/reviews
GET /ai-training-drafts?status=open
GET /ai-training-drafts?status=accepted
GET /emg/latest
GET /emg/history
GET /platform/sync-status
GET /platform/sync-runs
GET /offline-queue
GET /safety-audit
```

`GET /me` is the phone bootstrap endpoint. In addition to profile, devices, plans, active session, latest preflight, latest report, latest open AI draft, platform sync, and queued offline items, it returns `onboarding_guide`, `primary_start_guide`, `daily_action_guide`, `home_status_guide`, `care_summary`, `care_timeline`, `offline_sync_guide`, `session_recovery_guide`, `finished_session_report_guide`, `ai_draft_review_guide`, `report_followup_guide`, `device_operational_guide`, `safety_review_guide`, and `accepted_plan_guide`.

Use `onboarding_guide` for first-run setup. It gives ordered steps and `actions` for profile, trusted M33 device binding, and training plan creation/acceptance, with endpoint, method, and payload hints. Completed setup steps are omitted from `actions`, while `steps` keeps the full progress list. Use `primary_start_guide` for the home screen's main training CTA when setup basics exist; it is the same evidence-only guide returned by `start-guide` and now includes `actions` for `VIEW_START_GUIDE`, `CHECK_START_READINESS`, and the current start-blocker or start-record action.

Use `daily_action_guide` for the home screen's top action. It prioritizes unfinished training recovery, blocking safety review, finished-session report generation, queued/failed offline evidence handling, AI draft review, latest report review, report-to-next-plan drafting, normal training start guidance, and onboarding fallback. It is evidence-only and should not be treated as motion permission.

Use `home_status_guide` for the first phone card a user sees. It wraps the top action with user-facing `tone`, `headline`, `body`, `primary_action`, `secondary_actions`, `action_groups`, blockers, `blocker_details`, `primary_blocker`, counts, `progress`, and a safety note, so the frontend does not need to infer priority or severity from raw records. `secondary_actions` exposes deduped follow-up actions from the same source guide after removing the current primary action by code and endpoint/method. `action_groups.primary`, `action_groups.secondary`, and `action_groups.blocker_related` let the phone render buttons grouped by current blocker without maintaining its own code map. `primary_blocker` is the first backend-prioritized blocker detail, or `null` when no blocker exists. Each `blocker_details` item includes `clear_condition`, a user-facing explanation of the evidence or workflow step that clears the blocker. `progress` reports `stage`, `stage_title`, `stage_description`, `stage_tone`, `done`, `total`, `remaining`, `completion_percent`, `completion_label`, `remaining_label`, `next_item`, `next_item_position`, `next_item_label`, `next_item_actions`, `next_item_blockers`, `next_item_context`, and checklist items for onboarding, active-session clearance, safety review, finished-report generation, report review, AI drafts, offline evidence, and start readiness; each item includes `position`, `position_label`, `status`, `status_label`, `tone`, `title`, `description`, `related_blocker_codes`, and `related_action_codes` so phone/PWA/Stitch shells can render progress without local translation maps. Item statuses are backend-authored as `done`, `current`, or `pending`. `completion_percent` and labels describe the full home workflow checklist, not only the onboarding substeps. `next_item` follows `primary_blocker` first, otherwise the first incomplete progress item, and is `null` when all progress items are complete; `next_item_position` is 1-based for step indicators and becomes `null` when complete, while `next_item_label` is a display string such as `第 1/8 项` or `全部完成`. `next_item_actions` is the backend-filtered list of currently available actions whose codes match that highlighted progress item, and `next_item_blockers` is the matching blocker-detail list with severity and clear condition. `next_item_context` wraps the highlighted item, `display` copy (`title`, `description`, `tone`, `severity`, `clear_condition`), backend-selected `primary_action`, remaining `secondary_actions`, all matching actions, matching blockers, counts, and `app_home_progress_context_evidence_only_not_motion_permission`; it is `null` when all progress items are complete. This applies to active-session recovery, finished-session report generation, report follow-up, accepted AI plan sync/preflight, safety review, and offline evidence handling; for example, a failed offline queue card can show `VIEW_OFFLINE_QUEUE` first and keep both failed-item review and queued replay as secondary actions when both states coexist.

Use `care_summary` for home overview counters and status chips. It reports start readiness, active/finished/cancelled sessions, report review count, finished sessions waiting for report generation, pending safety reviews, open AI drafts, queued offline evidence, blockers, `blocker_details` with user-facing title/description, `severity`, `clear_condition`, and `related_action_codes`, plus `primary_blocker` for the highest-priority blocker. Blockers include `safety_review_required` for unreviewed critical safety events and `finished_report_required` for finished sessions that still need a report. It is a backend-composed summary of persisted records.
When setup is complete but the selected plan/device still cannot start, `care_summary.blockers` includes `start_readiness_blocked`; use its related actions to show start-guide, readiness, M33 sync/acceptance, preflight, or safety-review steps.

Use `care_timeline` for the recent history surface. It aggregates persisted training sessions, training reports, AI training drafts, and queued offline evidence items into timeline entries with source ids, status, timestamp, and compact details. It is read-only continuity evidence.

The phone `我的 / 训练活动` calendar must be driven by `care_timeline`, not by local demo values. The calendar highlights days only when persisted `training_session` entries exist, counts this week's real training sessions, and lists recent timeline evidence below the grid. If there are no real sessions this week, the expected user-facing state is `暂无本周训练记录` with a next-step button such as `去创建计划`; do not show hardcoded months, fake heatmap cells, or fake weekly counts.

Use `offline_sync_guide` to show queued/failed offline evidence counts and safe queue actions. When queued evidence exists it returns `REPLAY_OFFLINE_EVIDENCE` for `POST /api/rehab-arm/app/v1/offline-queue/replay`; when failed evidence exists it returns `review_failed_items`, `VIEW_OFFLINE_QUEUE` for `GET /api/rehab-arm/app/v1/offline-queue?status=failed`, and `REVIEW_FAILED_OFFLINE_ITEM` for `POST /api/rehab-arm/app/v1/offline-queue/{item_id}/review`. Failed-item review requires a non-empty `note` and `review_status` of `reviewed`, `ignored`, `duplicate`, or `replaced`; it only applies to `failed` items and cannot be used to skip queued evidence replay. Reviewed failed items keep their evidence and review note but no longer block the home action.

Use `session_recovery_guide` when `active_session` is present. It lists allowed evidence-state actions such as view, progress, finish, cancel, resume, or record safety review. A paused session with an unreviewed critical safety event returns `safety_review_required` instead of a direct resume action.

Use `finished_session_report_guide` when the latest finished session has no generated training report yet. It returns a `GENERATE_TRAINING_REPORT` action pointing to `POST /training-sessions/{session_id}/report`, then clears after the report exists so `report_followup_guide` can drive review and next-plan decisions.

Use `ai_draft_review_guide` when `latest_open_ai_draft` exists. It gives `VIEW_AI_DRAFT` and `ACCEPT_AI_DRAFT` actions so the phone can review and accept a draft from one backend-authored surface. Accepting the draft only creates a normal training plan; the App must still complete trusted-device binding, current-version M33 sync/acceptance, preflight, and start readiness before any training session record can start.

Use `report_followup_guide` when `latest_report` is present. It keeps the post-training loop backend-authored: record report review, generate a next-plan AI draft when requested, review/accept the open draft, then sync the accepted plan to M33. It is evidence and workflow guidance only, not motion permission.

Use `device_operational_guide` for the phone device card. It reports whether a trusted device is required, plan sync is required, M33 decision is pending, M33 rejected the latest sync, or M33 acceptance is ready. It includes latest diagnostic evidence and safe next actions such as bind device, upload diagnostic, request status, record M33 decision, resync after review, or check start readiness.

Use `safety_review_guide` for historical critical safety blockers. If a finished/cancelled/paused session still has an unreviewed critical event, it returns the blocking session/event plus actions to view events and record an approved/conditional `safety_review`. It does not release emergency stop or grant motion permission.

Use `accepted_plan_guide` after an AI draft has been accepted into a training plan. It routes the phone through trusted-device binding, M33 sync, M33 decision, preflight/readiness, and start-record creation. It closes the AI-planning loop without treating the accepted plan as execution permission.

### App AI 中转站调用

The App uses the same server-side model-provider configuration as the platform model relay, but it does not call or modify the XiaoZhi/L WebSocket path. Discover the App contract with:

```http
GET /api/rehab-arm/app/v1/public-config
```

Read `data.rehab_app.ai_relay_contract`. Expected values are `relay_channel=app_training_planner`, `client_type=app`, `purpose=training_plan_draft`, `scope=rehab_training_planning`, and `does_not_touch_xiaozhi_l=true`.

Phone UI:

- Open the mobile App `AI` tab / `ai-plan.html`, shown as `康复智能体`.
- Enter natural language needs such as `今天有点酸，下一次练轻一点`.
- Set pain and fatigue. The page sends these values through `data-arm-ai-input`, `data-arm-ai-pain`, and `data-arm-ai-fatigue` to the App backend.
- Tap `生成 AI 草稿`. The page binds the returned draft into `ai-draft-title`, `ai-draft-sets-reps`, `ai-draft-assist`, and `ai-draft-explain`.
- Tap `接受为训练计划` only after review. This creates a normal training plan and does not grant motion permission.
- During generation, the page disables accepting any previous draft so the user cannot accidentally approve stale history. After accepting, the page keeps showing the accepted plan and the next safety step instead of jumping to another open draft.
- Continue through device sync, M33 acceptance, and preflight before starting a training session record.

Call flow:

1. Login and keep the returned token.

```http
POST /api/auth/session
Authorization: none
Content-Type: application/json

{"email":"3245056131@qq.com","password":"1234"}
```

2. Ask the App planner for a draft. The API key for the external model stays on the server; the phone only sends training context.

```http
POST /api/rehab-arm/app/v1/ai-training-drafts/generate
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "input_text": "根据今天训练情况，生成下一次更安全的肘关节训练计划",
  "context_snapshot": {
    "movement_type": "elbow_flexion",
    "sets": 2,
    "reps": 6,
    "daily_training_summary": {
      "completed_sets": 2,
      "fatigue": "mild",
      "pain_after": 3
    },
    "latest_emg_summary": {
      "biceps": 0.62,
      "triceps": 0.31
    },
    "m55_intent_summary": {
      "predicted_action": "elbow_flexion",
      "confidence": 0.81
    }
  }
}
```

3. Inspect the draft and audit evidence:

```http
GET /api/rehab-arm/app/v1/ai-training-drafts?status=open
GET /api/rehab-arm/app/v1/safety-audit
```

4. Accept a draft only after human review:

```http
POST /api/rehab-arm/app/v1/ai-training-drafts/{draft_id}/accept
```

5. Sync the accepted plan to M33 and wait for M33 acceptance before starting a training session:

```http
POST /api/rehab-arm/app/v1/training-plans/{plan_id}/sync-to-device
POST /api/rehab-arm/app/v1/devices/{device_id}/m33-status
POST /api/rehab-arm/app/v1/training-sessions/start
```

The response draft contains `context_snapshot.ai_planner`. Use those fields for platform logs: `relay_channel=app_training_planner`, `client_type=app`, `purpose=training_plan_draft`, and `scope=rehab_training_planning`. The same metadata is also mirrored into `rehab_app.ai_training_draft.generated` audit events returned by `GET /safety-audit`, so platform viewers can show XiaoZhi/L and App AI records together while still filtering by client type, purpose, and scope. XiaoZhi/L records remain under model relay / voice relay / L mode logs, so App and XiaoZhi evidence can be displayed together without sharing control authority. The accepted `generated_plan` is sanitized before persistence: dangerous control-shaped keys for CAN, motors, current/torque, raw position/velocity, M33 override, or emergency-stop release are stripped from nested plan dictionaries.

Mobile diagnostic and offline replay:

```text
POST /devices/{device_id}/diagnostic-upload
POST /devices/{device_id}/ble/messages
POST /devices/{device_id}/ble/messages/{message_id}/ack
POST /training-sessions/{session_id}/report
POST /training-reports/{report_id}/reviews
POST /training-reports/{report_id}/draft-next-plan
POST /offline-queue
POST /offline-queue/replay
```

BLE messages are structured App-to-M33 contract records. They can prepare App hello, device status request, training plan push, training session start/progress/pause/stop request, and diagnostic snapshot request payloads. For the old tested Android transport, public config/catalog expose `m33_legacy_spp_profile`: Bluetooth Classic SPP/RFCOMM UUID `00001101-0000-1000-8000-00805F9B34FB`, UTF-8 JSON, newline delimiter. BLE-message payloads include `legacy_transport_frame`; phone native code should write `legacy_transport_frame.wire_text` only when `sendable=true`. They are not CAN or motor commands, and M33 ACKs are evidence only.

Training reports summarize session completion, EMG overview, M55 intent overview, M33 safety evidence, and review recommendations. Report reviews can record patient/therapist notes, next-step intent, and a request-new-plan flag. They are review records only and return `training_report_review_only_not_medical_diagnosis_or_motion_permission`.

The report-to-next-plan endpoint turns a finished report and latest review into an AI draft through the same App training-planner relay contract. It is useful after fatigue, pain, or therapist review indicates adjustment, but the output is still `ai_draft_only_not_execution_permission`. After the draft is accepted, run `sync-to-device`, wait for `m33_accepted`, and only then call `training-sessions/start`.

Platform sync accepts evidence resource types including `training_plans`, `training_sessions`, `training_reports`, `training_report_reviews`, `plan_constraint_reviews`, `session_safety_events`, `ai_training_drafts`, `emg_summaries`, and `m33_decisions`.

Allowed offline replay operations:

```text
device_diagnostic_upload
training_session_progress
session_safety_event
plan_constraint_review
emg_summary
intent_summary
platform_sync
```

Safety rule: these endpoints do not send CAN frames, motor current, motor torque, raw joint position/velocity, M33 overrides, or emergency-stop release commands. Every training/device response remains plan, evidence, or review data until M33 and the robot-side stack decide otherwise.

To unbind a paired M33 device, call `POST /api/rehab-arm/app/v1/devices/{device_id}/unbind` with an optional `reason`. The backend keeps history and diagnostics visible, but freezes the device as revoked so it cannot sync plans, send BLE messages, update M33 decisions, or start sessions.

Training sessions support evidence-state transitions:

```text
POST /api/rehab-arm/app/v1/training-sessions/{session_id}/pause
POST /api/rehab-arm/app/v1/training-sessions/{session_id}/resume
POST /api/rehab-arm/app/v1/training-sessions/{session_id}/cancel
```

Paused sessions still occupy the device and must be resumed before progress can be recorded. Cancelled sessions are ended and cannot be finished or turned into training reports. These endpoints record App workflow state only; the robot-side M33/firmware path remains responsible for any physical pause or stop behavior.

Record in-session safety evidence with:

```text
POST /api/rehab-arm/app/v1/training-sessions/{session_id}/safety-events
GET /api/rehab-arm/app/v1/training-sessions/{session_id}/safety-events
```

Allowed event types are `pain_report`, `device_fit_issue`, `m33_reject`, `fatigue_report`, `manual_stop_request`, `safety_review`, and `other`. A `critical` event, or a `pain_report` with `pain_score >= 7`, automatically pauses the App session state and blocks further progress writes until `resume` is called. Resume and the next start on the same device return `SAFETY_REVIEW_REQUIRED` until a later `safety_review` event is recorded with `payload.review_status` set to `approved` or `conditional`. This is workflow evidence only; robot-side stop authority still belongs to M33/firmware.

Archived or rejected training plans stay visible in history, but they cannot be synced to M33 and cannot start a training session. Create or reactivate an appropriate plan, sync the current version, and wait for `m33_accepted` before starting.

Plans that clearly conflict with profile `medical_constraints` are blocked before sync/start with `TRAINING_PLAN_CONTRAINDICATED`. For example, `no overhead motion` blocks shoulder/overhead plans or ranges above 90 degrees. A therapist-reviewed plan must create evidence with `POST /api/rehab-arm/app/v1/training-plans/{plan_id}/constraint-reviews`; reviews can be read with `GET /api/rehab-arm/app/v1/training-plans/{plan_id}/constraint-reviews`. Reviews are tied to the current plan version, so editing the plan requires a fresh review. Reviewed plans still must be synced to M33, accepted by M33, and pass preflight before a session can start.

Before starting a training session, submit a preflight check:

```text
POST /api/rehab-arm/app/v1/training-preflight
```

Required checklist keys are `device_worn_correctly`, `pain_within_limit`, `stop_explained`, and `m33_plan_accepted`, all set to `true`. The preflight must reference the current `plan_id`, `device_id`, and accepted `sync_id`; editing the plan or getting a new M33 decision requires a fresh preflight.

Read recent preflight evidence with `GET /api/rehab-arm/app/v1/training-preflight`, optionally filtered by `plan_id` and `device_id`. `GET /api/rehab-arm/app/v1/me` returns `latest_preflight` and also returns a paused training session as `active_session`, so the phone App can recover after restart without creating a second session.

If patient-submitted `pain_before` is at least 2 points above `pain_baseline`, or is 7 or higher, the backend returns `PREFLIGHT_PAIN_REVIEW_REQUIRED`. The App should stop the start flow and ask for therapist review. A therapist preflight can be submitted with `checked_by_role=therapist`; it is still evidence only and does not bypass M33 authority.

Before enabling the start action, read:

```text
GET /api/rehab-arm/app/v1/training-plans/{plan_id}/readiness?device_id={device_id}
```

The response returns `can_start` plus named checks for plan usability, revoked device state, profile constraints, active session conflicts, M33 acceptance, preflight, and required safety review. Use the check `code` values for user-facing guidance. The readiness response is `training_readiness_evidence_only_not_motion_permission`; it is not a robot-side motion permit.

For a user-facing guide, read:

```text
GET /api/rehab-arm/app/v1/training-plans/{plan_id}/start-guide?device_id={device_id}
```

The guide embeds readiness and returns `next_action` plus ordered `steps`. `next_action` can point the App to plan selection, device binding, constraint review, active-session recovery, M33 plan sync, preflight, safety review, or `training-sessions/start` when ready. Treat it as phone workflow guidance only; it does not create a session and does not command hardware.

## Android APK Build Environment

This workstation has the Android build prerequisites installed for the rehab-arm mobile wrapper:

```text
JAVA_HOME=D:\Java\jdk-21
ANDROID_HOME=D:\Android\Sdk
ANDROID_SDK_ROOT=D:\Android\Sdk
```

Installed Android SDK packages:

```text
platform-tools 37.0.0
build-tools 35.0.0
platforms;android-35
emulator 36.6.11
```

For a fresh PowerShell session, load the environment with:

```text
.\scripts\use-android-build-env.ps1
```

Then verify:

```text
java -version
javac -version
adb version
sdkmanager.bat --list_installed
```

## Rehab Arm Android APK

Current debug APK download:

```text
http://106.55.62.122:3001/downloads/rehab-arm/lingdong-rehab-arm-debug.apk
```

APK details:

```text
package: com.lingdong.rehabarm
label: 灵动康复 ArmControl
version: 1.0.9 debug
versionCode: 10
size: 4,189,022 bytes
sha256: 155EEBB6B4FA1C001DD82744B3F4A92356B757784EBC3778444F755AA2C020BF
```

Android may warn that this debug build is from an unknown source. This is expected for the current unsigned-store debug APK. Use it only for internal testing.

Current user-release gate:

```text
status: blocked
reason: APK 1.0.9 connects to backend public-config/catalog/bootstrap/workflow, renders backend care timeline/daily workflow state, can execute safe workflow actions, includes the Android native Bluetooth Classic SPP bridge, and exposes a Stitch-designed Bluetooth debug / M33 validation page that can bind a paired SPP device as a backend trusted device. Current M33 firmware compatibility and physical phone-to-M33 ACK validation are still pending.
hardware_protocol: legacy SPP profile available; UUID 00001101-0000-1000-8000-00805F9B34FB with newline-delimited UTF-8 JSON. Real Android pairing, backend device binding, frame send, and ACK/sensor evidence must be tested on hardware before motion-adjacent UX can be certified.
```

Backend readiness endpoints:

```text
GET /api/rehab-arm/app/v1/public-config
GET /api/rehab-arm/app/v1/me
GET /api/rehab-arm/app/v1/me/workflow
POST /api/rehab-arm/app/v1/me/workflow/actions
```

`public-config.release_gate.checks` reports the install-package release blockers. Authenticated `/me.mobile_readiness_guide` reports account onboarding, device, plan, M33/preflight, offline evidence, safety review, APK wiring, old SPP protocol availability, and native phone-bridge blockers. These responses are workflow/evidence guidance only and do not grant Bluetooth send authority, CAN, motor, or M33 override authority.

Authenticated `/me.daily_care_plan` is the phone home source for the user's current daily checklist. It includes the primary task, next action, blocker details, progress totals, counts, and a short care-timeline preview. Frontend shells should render this field instead of using demo progress cards or recomputing the task order.

Use `/me/workflow/actions` with JSON like `{"action_code":"GENERATE_TRAINING_REPORT","payload":{}}`. The backend only executes actions present in the current workflow queue and rejects forbidden motion/hardware actions such as direct motor commands, CAN frame send, M33 override, emergency-stop release, M33 decision spoofing, or App-granted motion permission.

Each item in `/me/workflow.action_queue` may include `payload_schema` and `form_contract`. Phone shells should render profile, trusted-device, training-plan, preflight, progress, finish-session, report-review, offline, and sync forms from these backend fields, then submit to `/me/workflow/actions`; do not hard-code demo payloads in the APK/PWA.

Bluetooth debug / M33 validation page:

```text
Device page -> 蓝牙调试 / 实机验证
```

On an Android install, first pair the M33/PSoC SPP device in system Bluetooth settings. Then open the App, log in, enter the device page, open `蓝牙调试 / 实机验证`, tap `读取已配对设备`, tap `绑定` on the target device to write it to `/devices/bind`, tap `连接`, sync a training plan to generate a backend `legacy_transport_frame`, then tap `发送后端批准帧`. The page should show TX/RX/API evidence after `memory_ack`, `execute_ack`, `sensor`, or `error` returns from M33. In normal browser/PWA mode it should show `仅 Web/无权限`, because Web Bluetooth does not support Classic SPP.

Safety boundary: the debug page does not expose CAN frames, raw motor commands, motor current/torque/position/velocity, M33 override, or emergency-stop release. SPP ACKs prove transport/device response only; they do not automatically mark a plan as M33-accepted.

Rebuild locally:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\use-android-build-env.ps1
cd apps\mobile\rehab-arm-android
npm install
npm run build:debug
```

Local APK output:

```text
apps/mobile/rehab-arm-android/android/app/build/outputs/apk/debug/app-debug.apk
```

## Rehab Arm Control Room AI Model Module

On the rehab-arm control-room page, open the `AI模型` workspace from the top navigation or left module rail. The model relay console now stays inside the same control-room page and includes provider configuration, high-level prompt suggestions, restricted device token generation, HTTP/XiaoZhi endpoints, and relay audit events.

Safety rule: AI model output is review/dry-run evidence only. It does not send CAN frames, motor current, motor torque, raw joint position/velocity, M33 overrides, or emergency-stop release commands.

## Rehab Arm Cloud Backend Verification

Current cloud backend deployment:

```text
Web: http://106.55.62.122:3001
API: http://106.55.62.122:8011
build_sha: 17d7e78b2b10
build_ref: app/rehab-arm-mobile-stitch
```

Verify Web/API alignment:

```powershell
python scripts\check_web_api_alignment.py --web-base http://106.55.62.122:3001 --api-base http://106.55.62.122:8011 --project-id e201f41c-25a6-46e1-baf8-be6dcb83284c
```

Pass criteria: `ok` is `true`, direct API and Web proxy deployment metadata match, and `/api/rehab-arm/app/v1/me` returns workflow guidance only. App HTTP responses do not grant BLE, CAN, motor, or M33 override authority.
