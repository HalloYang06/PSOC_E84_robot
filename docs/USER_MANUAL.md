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

`GET /me` is the phone bootstrap endpoint. In addition to profile, devices, plans, active session, latest preflight, latest report, latest open AI draft, platform sync, and queued offline items, it returns `onboarding_guide`, `primary_start_guide`, `daily_action_guide`, `care_summary`, `care_timeline`, `offline_sync_guide`, `session_recovery_guide`, `finished_session_report_guide`, `report_followup_guide`, `device_operational_guide`, `safety_review_guide`, and `accepted_plan_guide`.

Use `onboarding_guide` for first-run setup. It gives ordered steps for profile, trusted M33 device binding, and training plan creation/acceptance, with endpoint, method, and payload hints. Use `primary_start_guide` for the home screen's main training CTA when setup basics exist; it is the same evidence-only guide returned by `start-guide`.

Use `daily_action_guide` for the home screen's top action. It prioritizes unfinished training recovery, blocking safety review, finished-session report generation, queued/failed offline evidence handling, AI draft review, latest report review, report-to-next-plan drafting, normal training start guidance, and onboarding fallback. It is evidence-only and should not be treated as motion permission.

Use `care_summary` for home overview counters and status chips. It reports start readiness, active/finished/cancelled sessions, report review count, open AI drafts, queued offline evidence, and blockers. It is a backend-composed summary of persisted records.

Use `care_timeline` for the recent history surface. It aggregates persisted training sessions, training reports, AI training drafts, and queued offline evidence items into timeline entries with source ids, status, timestamp, and compact details. It is read-only continuity evidence.

Use `offline_sync_guide` to show queued/failed offline evidence counts and safe queue actions. When queued evidence exists it returns `REPLAY_OFFLINE_EVIDENCE` for `POST /api/rehab-arm/app/v1/offline-queue/replay`; when failed evidence exists it returns `review_failed_items`, `VIEW_OFFLINE_QUEUE` for `GET /api/rehab-arm/app/v1/offline-queue?status=failed`, and `REVIEW_FAILED_OFFLINE_ITEM` for `POST /api/rehab-arm/app/v1/offline-queue/{item_id}/review`. Reviewed failed items keep their evidence and review note but no longer block the home action.

Use `session_recovery_guide` when `active_session` is present. It lists allowed evidence-state actions such as view, progress, finish, cancel, resume, or record safety review. A paused session with an unreviewed critical safety event returns `safety_review_required` instead of a direct resume action.

Use `finished_session_report_guide` when the latest finished session has no generated training report yet. It returns a `GENERATE_TRAINING_REPORT` action pointing to `POST /training-sessions/{session_id}/report`, then clears after the report exists so `report_followup_guide` can drive review and next-plan decisions.

Use `report_followup_guide` when `latest_report` is present. It keeps the post-training loop backend-authored: record report review, generate a next-plan AI draft when requested, review/accept the open draft, then sync the accepted plan to M33. It is evidence and workflow guidance only, not motion permission.

Use `device_operational_guide` for the phone device card. It reports whether a trusted device is required, plan sync is required, M33 decision is pending, M33 rejected the latest sync, or M33 acceptance is ready. It includes latest diagnostic evidence and safe next actions such as bind device, upload diagnostic, request status, record M33 decision, resync after review, or check start readiness.

Use `safety_review_guide` for historical critical safety blockers. If a finished/cancelled/paused session still has an unreviewed critical event, it returns the blocking session/event plus actions to view events and record an approved/conditional `safety_review`. It does not release emergency stop or grant motion permission.

Use `accepted_plan_guide` after an AI draft has been accepted into a training plan. It routes the phone through trusted-device binding, M33 sync, M33 decision, preflight/readiness, and start-record creation. It closes the AI-planning loop without treating the accepted plan as execution permission.

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

BLE messages are structured App-to-M33 contract records. They can prepare App hello, device status request, training plan push, training session start/progress/pause/stop request, and diagnostic snapshot request payloads. They are not CAN or motor commands, and M33 ACKs are evidence only.

Training reports summarize session completion, EMG overview, M55 intent overview, M33 safety evidence, and review recommendations. Report reviews can record patient/therapist notes, next-step intent, and a request-new-plan flag. They are review records only and return `training_report_review_only_not_medical_diagnosis_or_motion_permission`.

The report-to-next-plan endpoint turns a finished report and latest review into an AI draft. It is useful after fatigue, pain, or therapist review indicates adjustment, but the output is still `ai_draft_only_not_execution_permission`. After the draft is accepted, run `sync-to-device`, wait for `m33_accepted`, and only then call `training-sessions/start`.

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
version: 1.0
sha256: C80F78CE4CCF315368ADC13C178E40CA620B2CD3A7CF48EC751CF42F72CB84ED
```

Android may warn that this debug build is from an unknown source. This is expected for the current unsigned-store debug APK. Use it only for internal testing.

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
