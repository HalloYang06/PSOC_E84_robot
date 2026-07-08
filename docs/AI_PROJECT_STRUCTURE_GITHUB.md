# AI Project Structure GitHub

## Rehab Arm Control Room / VLA Console Slice

Cloud route:

- `http://106.55.62.122:3001/projects/e201f41c-25a6-46e1-baf8-be6dcb83284c/rehab-arm-control`

Frontend ownership:

- Stitch owns the visual pages under `apps/web/public/rehab-stitch/`.
- Codex owns data binding, module navigation, safety boundaries, exports, deployment, and QA in `apps/web/app/projects/[id]/rehab-arm-control/rehab-arm-control-client.tsx`.
- Do not replace Stitch pages with hand-written dashboard/card layouts. Preserve the Stitch page first, then wire existing functions into its `data-role` slots.

Current same-level modules:

- `CMD / 总控`: overall VLA control room.
- `V / 视觉`: backend camera/keyframe/stereo evidence only; no fake frontend boxes.
- `3D / 孪生`: URDF/Three.js stage plus MuJoCo/robot-render evidence. Imported URDF models are shown in MuJoCo-shadow metric/root coordinates; the browser camera frames the model instead of re-centering or re-scaling the model geometry.
- `EMG / 肌电`: upper-limb muscle/EMG/M55 intent evidence.
- `AI / 模型`: inline model relay module using `apps/web/public/rehab-stitch/model-lab.html`.
- `L / 模式`: XiaoZhi/L semantic routing and shared-resource dispatch.
- `TRN / 训练`: APP/M33/M55 training-library chain.
- `DATA / 数据`: dataset asset loop using `apps/web/public/rehab-stitch/data.html`; capture, annotation, model-training feedback, and full robotics workbench entry.
- `A / 动作`: dry-run action planning and safety gate evidence.
- `IO / 诊断`: NanoPi/CAN/M33/M55/platform diagnostics.
- `LOG / 日志`: evidence timeline.

IK / digital-twin evidence boundary:

- `3D / 孪生` now includes an IK dry-run evidence slot inside the Stitch page `apps/web/public/rehab-stitch/twin.html`.
- The visible Stitch URDF upload control in `twin.html` is bridged into the real React `Arm3DOverview` loader through an external file request. Do not update only the Stitch label; successful import must also update the real Three.js/URDF portal host (`#codex-twin-runtime-stage`) and parse joints in the `Arm3DOverview` state.
- The browser can submit `target_robot_frame: {x_m, y_m, z_m}`, optional `approach_vector`, optional `gripper_orientation`, and `source = vision_calibrated | manual_platform | simulation_test` to the platform API. This is for candidate generation and review only.
- The API returns `rehab_arm_ik_candidate_evidence_v1` with `ik_status`, `candidate_joint_trajectory`, `ik_solver_report`, `joint_limit_check`, `collision_or_workspace_check`, `simulation_result`, and `control_boundary = ik_candidate_evidence_only_not_motion_permission`.
- Current joint naming follows the MuJoCo shadow chain order: `jian_hengxiang_joint`, `jian_zongxiang_joint`, `jian_xuanzhuan_joint`, `zhou_zongxiang_joint`, `wanbu_zongxiang_joint`, `wanbu_hengxiang_joint`. Motor IDs `3/4/5/6` are wired evidence sources; wrist IDs `1/2` remain pending. When consuming older payloads, map by joint name rather than array index.
- The backend candidate solver now uses a damped-least-squares numerical IK pass over the remote MuJoCo 6DOF shadow chain. FK maps by joint name and uses MuJoCo order `jian_hengxiang_joint`, `jian_zongxiang_joint`, `jian_xuanzhuan_joint`, `zhou_zongxiang_joint`, `wanbu_zongxiang_joint`, `wanbu_hengxiang_joint`; `robot_render_state_v1` is also emitted in this order for new platform-generated render state.
- The `3D / 孪生` IK coordinate panel keeps a local draft while the Stitch iframe refreshes. Dashboard polling or manual refresh must not overwrite the operator's unsent `target_robot_frame`, approach vector, gripper orientation, or source selection.
- The solver uses remote MuJoCo 6DOF shadow limits from `192.168.3.34`: `jian_hengxiang_joint [-0.7854,1.5708]`, `jian_zongxiang_joint [-0.5236,1.7453]`, `jian_xuanzhuan_joint [-1.0472,1.0472]`, `zhou_zongxiang_joint [0.0,2.3562]`, `wanbu_zongxiang_joint [-0.7854,0.7854]`, and `wanbu_hengxiang_joint [-0.3491,0.5236]`. Solver status is residual-based (`candidate_ready`, `candidate_approximate`, or `candidate_blocked`).
- The response includes `mujoco_shadow_validation_plan` for the remote Linux host. It targets only `/sim/medical_arm/joint_trajectory` and observes `/sim/medical_arm/joint_states` under `ROS_DOMAIN_ID=42`; it explicitly must not publish `/arm_controller/joint_trajectory`, `/joint_states`, CAN, or motor bus outputs.
- IK output is not motion permission. Real movement still requires `L instruction -> V target/coordinate -> A candidate -> MuJoCo/URDF validation -> M33 safety decision -> NanoPi/M33 hardware chain`.
- The platform must not add buttons or endpoints for direct motion, CAN send, raw motor setpoints, emergency-stop release, or M33 override.

Stereo depth / camera-to-robot evidence boundary:

- `V / 视觉` owns ordinary dual-USB RGB camera evidence. NanoPi or the local capture workstation may upload `stereo_left` and `stereo_right` keyframes plus a `stereo_rgb_yolo_context_v1` record; the platform consumes those records as read-only V evidence.
- The first valid stereo calibration artifact must include left/right intrinsics, distortion, rectification/extrinsics `R/T`, image size, baseline, reprojection error, `calibration_id`, and creation time. Calibration output should be stored as versioned JSON/YAML evidence, not as hardcoded constants in the UI.
- Current first metric bench artifact is `chessboard_real_20260703_01_A4_20mm_9x6`, produced from the A4 PDF `zhang_chessboard_9x6_inner_20mm_A4.pdf` with `9x6` inner corners and `20 mm` squares. The NanoPi artifact path is `/home/pi/rehab_arm_stereo_calibration/calibrations/chessboard_real_20260703_01_A4_20mm_9x6.json` / `.yaml`, and it reports `baseline_m=0.06276126842552868` with `reprojection_error=0.4277624184705839`.
- Before stereo calibration is present, `estimated_depth_m`, `target_3d_camera_frame`, and `target_3d_robot_frame` must stay `null`, `waiting`, or equivalent. A 6 cm physical baseline can be displayed as setup context, but it must not be treated as calibrated metric depth.
- After stereo calibration, V may publish `target_3d_camera_frame: {x_m, y_m, z_m}` plus `disparity_px`, target/end-effector labels, bbox/center evidence, multi-frame lock state, and `control_boundary = stereo_depth_evidence_only_not_motion_permission`.
- Stereo evidence should carry the capture mapping that produced logical `stereo_left` and `stereo_right`: OpenCV camera indices when known, left/right frame flip (`none/h/v/hv/unknown`), and whether orientation was applied before detection/depth. If physical indices are not confirmed, the mapping state must remain waiting instead of inventing `/dev/video*` truth.
- Camera-to-robot hand-eye calibration is a separate gate. Only after a current `camera_to_robot_transform` exists may V also publish `target_3d_robot_frame: {x_m, y_m, z_m}` and mark `camera_to_robot_ready = true`.
- Target quality gates must remain explicit: no target, low confidence, poor bbox size, stale frame, missing right-eye match, missing end-effector, or unstable multi-frame lock should hold the A side at `hold_observe`.
- The platform must not draw fake frontend detection boxes. Any visible boxes, labels, or annotated frames must originate from backend OpenCV/C++/YOLO output or true bbox payload fields. If no real detection exists, show `waiting`, `unknown`, or the actual rejection reason.

V-to-A coordinate handoff:

- V produces perception evidence: image pair, calibration state, target/end-effector observations, optional `target_3d_camera_frame`, and optional calibrated `target_3d_robot_frame`.
- A/IK consumes only `target_3d_robot_frame` or manually entered `target_robot_frame` when producing `rehab_arm_ik_candidate_evidence_v1`.
- If only camera-frame coordinates exist, A may display them for review but must not label them as robot-frame coordinates and must not generate a robot-frame motion candidate unless a safe manual/simulation target source is explicitly selected.
- The same A schema must support both real V coordinates and no-target manual platform coordinates for demos: `source = vision_calibrated | manual_platform | simulation_test`.
- Every handoff object should carry freshness, calibration id, source, confidence or quality gate, and a control boundary so logs can prove why A generated or refused a candidate.
- Dashboard devices expose `vla_closed_loop_status` (`rehab_arm_vla_closed_loop_status_v1`) as the unified read-only L/V/A/SIM/M33 explanation layer. It summarizes `active_mode`, `action_state`, `next_step`, `blockers`, and a five-stage `pipeline` (`L`, `V`, `A`, `SIM`, `M33`) with per-stage readiness and `control_boundary = vla_closed_loop_status_only_not_motion_permission`.
- `vla_closed_loop_status` must stay explanatory only. It may tell the platform why the current state is `hold_observe`, `ready_for_ik`, `ready_for_shadow_review`, `dry_run_review_ready`, or `candidate_review_ready`; it must not grant motion, publish ROS hardware topics, send CAN frames, bypass M33, or reinterpret camera-frame coordinates as robot-frame coordinates.

Next closed-loop AI ownership:

- Stereo-depth AI owns `camera frames -> stereo calibration -> depth -> camera-frame point -> optional robot-frame point`. It may edit NanoPi/capture scripts, stereo evidence schemas, V/DATA Stitch data slots, and calibration documentation. It must not edit XiaoZhi/L transport, M33/M55 firmware, CAN control, or IK solver authority.
- IK/platform-loop AI owns `robot-frame target -> IK candidate -> joint-limit/workspace/simulation evidence -> A dry-run export -> 3D Stitch display`. It may edit platform IK endpoints, digital-twin/A page data binding, MuJoCo shadow validation, and IK documentation. It must not fake V coordinates, bypass M33, or publish to hardware-control ROS/CAN topics.
- Both AIs must first read this document plus `docs/PROJECT_PROGRESS.md`, `docs/TROUBLESHOOTING_AND_LESSONS.md`, `docs/rehab-arm-nanopi-vla-mujoco-integration.md`, and the relevant `apps/web/public/rehab-stitch/*.html` page before editing.
- Frontend changes for both AIs must be Stitch-first. Use Stitch MCP to generate or refine the visual page, then wire data into `data-role` slots. Do not replace the command center with hand-built card piles.
- Shared resources should stay shared: one L semantic router, one V evidence layer, one A dry-run planner, one 3D/MuJoCo shadow path, one EMG/M55 evidence path, one App/M33 training path, one DATA asset loop, and one LOG evidence stream.

Platform / NanoPi / Linux host communication:

- Platform to NanoPi should continue through the existing read-only upload/dashboard pattern: camera keyframes, `stereo_vision_context`, device status, diagnostic records, and recent events. Do not add a parallel command bus for V or IK.
- NanoPi vision scripts should remain compatible with `scripts/nanopi-rehab-arm-readonly-agent.py` and `scripts/nanopi-rehab-arm-collect-and-upload.py`; performance-sensitive image processing may be added in C++/OpenCV, with Python used for orchestration/upload.
- Platform to the Linux simulation host (`192.168.3.34`) should use the existing MuJoCo shadow boundary. The shadow plan may target `/sim/medical_arm/joint_trajectory` and observe `/sim/medical_arm/joint_states` under the documented ROS domain, but must not publish hardware topics such as `/arm_controller/joint_trajectory`, direct `/joint_states`, CAN, or motor bus outputs.
- M33 remains the only final safety authority for real motion. M55/XiaoZhi and EMG are intent/evidence sources. The browser may route modes, display evidence, export JSON, and request dry-run candidates only.

DATA evidence boundary:

- The same-level `DATA / 数据` module binds stereo keyframe availability, L summaries, target/end-effector label status, EMG/M55 source status, MuJoCo/diagnostic event counts, and the full robotics data/annotation workbench entry.
- Exported snapshots use `dataset_evidence_only_not_motion_permission` and list expected labels such as `water_bottle`, `end_effector`, and `gripper_tip`.
- DATA workbench actions should route to existing robotics tabs: capture -> `tab=camera`, annotation -> `tab=dataset`, training/model -> `tab=model`, evaluation -> `tab=chart`.
- L semantic routing should send `data_collection` to the same-level `DATA / 数据` module, not back to `V / 视觉`; `V` remains shared visual evidence for planning and servo context.
- DATA is an asset/review loop only. It may open the full data workbench and export evidence, but it must not send CAN frames, raw motor setpoints, torque/current, raw position/velocity, M33 overrides, or emergency-stop release commands.

LOG evidence boundary:

- The same-level `LOG / 日志` module uses `apps/web/public/rehab-stitch/logs.html` as the visual source of truth and binds the live event stream, keyframes, raw packet viewer, refresh, copy, evidence export, and navigation into `V / 视觉`, `AI / 模型`, and `IO / 诊断`.
- Exported snapshots use `logs_evidence_export_only_not_motion_permission` and may include current L/V/A summaries, keyframe availability, dry-run gate state, recent events, and M33 final-authority status.
- The log page is review/evidence only. It must not send CAN frames, raw motor setpoints, torque/current, raw position/velocity, M33 overrides, or emergency-stop release commands.

AI model relay boundary:

- The inline `AI / 模型` module may save provider/model configuration, request high-level relay suggestions, show filtered relay output, generate/copy scoped relay tokens, display HTTP/XiaoZhi endpoints, and export `model_relay_evidence_only_not_motion_permission` JSON evidence.
- Vendor API keys remain server-side.
- Model output is suggestion/dry-run/evidence only. The browser must not send CAN frames, raw motor setpoints, torque/current, raw position/velocity, M33 overrides, or emergency-stop release commands.
- `/model-relay-lab` remains the advanced/full lab route, but normal VLA demos should use the same-level `AI / 模型` module instead of navigating away from the control room.

Shared AI relay split:

- The platform may use one server-side provider configuration (`REHAB_ARM_MODEL_RELAY_*`) for both XiaoZhi/L and App training planning, but the records must be separated by channel metadata.
- XiaoZhi/L route: `client_type = xiaozhi`, `purpose = semantic_route`, `scope = vla_mode_dispatch`. It consumes M55/XiaoZhi voice or transcript input, writes `model_relay_response`, `vla_language_context`, `vla_language_gate`, and XiaoZhi session evidence, and may classify modes such as `chat`, `fetch_object`, `training`, `assistive_emg`, `vision_servo`, `diagnostics`, or `data_collection`. It must not be changed by App training-planner work.
- App route: `client_type = app`, `relay_channel = app_training_planner`, `purpose = training_plan_draft`, `scope = rehab_training_planning`. It is exposed through `/api/rehab-arm/app/v1/ai-training-drafts/generate` and `/api/rehab-arm/app/v1/training-reports/{report_id}/draft-next-plan`, writes `rehab_app_ai_training_draft` records plus `rehab_app.ai_training_draft.generated` audit events, and returns high-level training-plan drafts only. Both App AI entry points must store the same channel metadata in `context_snapshot.ai_planner`, and the generated audit event `after` payload must repeat `relay_channel`, `client_type`, `purpose`, and `scope` so platform logs can display App planning beside XiaoZhi/L records without merging their control chains.
- Shared visibility is allowed in the control room logs and model pages, but shared visibility is not shared authority. XiaoZhi can route a language mode; App can draft a rehabilitation plan; neither path grants real motion, direct CAN, raw motor command, M33 override, emergency-stop release, or App-granted motion permission.
- App public config exposes `rehab_app.ai_relay_contract`, including `relay_channel = app_training_planner`, so phone/PWA/native shells can discover the App planner endpoints without reusing XiaoZhi WebSocket or L transport details.

## Rehab Arm Mobile App Slice

Branch: `app/rehab-arm-mobile-stitch`

Stitch project: `projects/9733571660387876930` (`灵动康复 ArmControl`)

Phone target:

- First runnable target is a mobile Web/PWA at `apps/web/public/rehab-arm-mobile/index.html`.
- The phone App is not Python. Python/FastAPI owns the backend API only.
- The current internal-test Android package wraps the same PWA surface with Capacitor under `apps/mobile/rehab-arm-android`; APK `1.0.13` includes the repaired profile phone-binding bootstrap plus Agent/device page `/me.profile` compatibility and still remains blocked on real M33/SPP hardware validation.
- Real phone-to-M33 transport uses the old verified Android App protocol when enabled: Bluetooth Classic SPP/RFCOMM UUID `00001101-0000-1000-8000-00805F9B34FB`, UTF-8 newline-delimited JSON. Browser/PWA JavaScript cannot open RFCOMM directly, so the Android package needs a native bridge before this becomes a usable hardware path.

Frontend ownership:

- Stitch owns visual layout and screen language.
- Codex owns integration, backend contracts, safety boundaries, offline/PWA wiring, and QA.
- Local Stitch-derived pages live in `apps/web/public/rehab-arm-mobile/`.
- `mobile-bridge.js` may add navigation, data binding, and safe action handlers, but should not redesign the screens.

Backend ownership:

- Mobile-facing API namespace: `/api/rehab-arm/app/v1`.
- Router/service/schema files:
  - `apps/api/app/modules/rehab_arm/app_router.py`
  - `apps/api/app/modules/rehab_arm/app_service.py`
  - `apps/api/app/modules/rehab_arm/app_schemas.py`
- Database models: `apps/api/app/db/models/rehab_arm_app.py`.
- Tests: `apps/api/tests/test_rehab_arm_app_backend.py`.

Safety boundary:

- App profile, device binding, training library, plan sync, sessions, EMG summaries, and M55 intent summaries are evidence/service data.
- Training-plan sync means a structured plan was submitted to M33 review. It is not motion permission.
- The backend exposes `m33_legacy_spp_profile` and may generate `legacy_transport_frame` records from the safe App BLE-message contract. The phone native bridge may send only frames with `sendable=true`; status/hello/diagnostic messages that are not part of the old SPP command set have `wire_text=null`.
- Old SPP frames are compatibility transport, not App-granted motion permission. `training_session_start_request` still requires current-version `m33_accepted`, and M33/firmware remains responsible for final hardware safety.
- The App and API must not expose CAN frames, raw motor setpoints, torque/current commands, raw motor position/velocity commands, M33 overrides, or emergency-stop release commands.
- M33 remains the final safety authority before any real motion.

Current validation:

- `python -m pytest tests/test_rehab_arm_app_backend.py -q` passes from `apps/api`.
- Mobile PWA preview runs from `apps/web/public` with `python -m http.server 4177 --bind 127.0.0.1`, then open `http://127.0.0.1:4177/rehab-arm-mobile/index.html`.

Closed-loop backend contract:

- `GET /api/rehab-arm/app/v1/me` returns the phone bootstrap payload: profile, devices, plans, active session, latest EMG, latest training report, latest open AI draft, platform sync status, and a control boundary.
- `GET /api/rehab-arm/app/v1/devices/{device_id}/status` returns M33-facing state for the bound device.
- `POST /api/rehab-arm/app/v1/devices/{device_id}/m33-status` records M33 sync decisions (`sent`, `m33_accepted`, `m33_rejected`, `failed`) and reasons. It records safety authority evidence; it does not expose override controls.
- Device bindings with `trust_status=revoked` remain visible for diagnostics/audit, but are blocked from plan sync, BLE messages/ACKs, M33 decision updates, and training session start with `DEVICE_REVOKED`.
- Training-plan edits increment `version`. `sync-to-device` captures `plan_version`, and `training-sessions/start` requires an `m33_accepted` sync for the current plan version on the selected device.
- A bound device can have only one active App training session (`started` or `in_progress`) at a time. Duplicate starts return `ACTIVE_TRAINING_SESSION_EXISTS` until the active session is finished or recovered.
- Finished training sessions are locked for progress/finish updates. Later report, review, and next-draft steps read the locked session evidence instead of mutating it.
- Once a training report exists for a session, late EMG/intent uploads for that session are rejected with `TRAINING_REPORT_ALREADY_GENERATED`; repeated report generation returns the existing report instead of recalculating it.
- AI training draft endpoints are draft-only: generate, list by `all/open/accepted`, read, accept-to-plan. Accepted drafts become normal training plans and still require M33 sync and acceptance before a training session record can start.
- App AI training drafts reuse the server-side model relay provider settings but carry `relay_channel=app_training_planner`, `client_type=app`, `purpose=training_plan_draft`, `scope=rehab_training_planning`, and `does_not_touch_xiaozhi_l=true` in `context_snapshot.ai_planner`. These fields are required for both direct draft generation and report-to-next-plan drafts, and are mirrored into `rehab_app.ai_training_draft.generated` audit logs so platform viewers can filter App training planning separately from XiaoZhi/L semantic routing.
- App康复师 Agent messages use `POST /api/rehab-arm/app/v1/agent/messages`. They are separate from the training planner and XiaoZhi/L: records carry `relay_channel=app_rehab_agent`, `client_type=app`, `purpose=rehab_agent_chat`, `scope=patient_training_guidance`, and `does_not_touch_xiaozhi_l=true`. Agent answers are advice only and must refuse CAN, motor, M33 override, emergency-stop release, or direct motion requests.
- Before an AI draft can become a training plan, the generated plan body is recursively stripped of dangerous control-shaped keys such as CAN frame, motor command/current/torque, raw position/velocity, M33 override, and emergency-stop release variants. The original request context may remain evidence, but accepted plans must not carry these keys in `generated_plan`.
- Platform sync endpoints are evidence/review only and must not be interpreted as motion permission.
- Diagnostic upload endpoints store M33/mobile snapshots for review: `POST /devices/{device_id}/diagnostic-upload` and `GET /devices/{device_id}/diagnostics`.
- Offline queue endpoints (`POST/GET /offline-queue`, `POST /offline-queue/replay`) are evidence-only. The replay whitelist is limited to diagnostic upload, training-session progress, EMG summary, M55 intent summary, and platform sync; motor or CAN-like operations are rejected.
- Training report endpoints close the post-session review loop: `POST /training-sessions/{session_id}/report`, `GET /training-sessions/{session_id}/report`, `GET /training-reports`, and `GET /training-reports/{report_id}`. Reports can only be generated after a session is `finished`, aggregate session/EMG/M55/safety evidence, and carry `training_report_review_only_not_medical_diagnosis_or_motion_permission`.
- Training report review endpoints close the human review step after a report exists: `POST /training-reports/{report_id}/reviews` and `GET /training-reports/{report_id}/reviews`. Reviews can record patient/therapist/family/engineer notes, next-step intent, and whether a new plan is requested; they remain review evidence and do not create motion permission.
- Report-to-next-plan drafting closes the review feedback loop without granting control: `POST /training-reports/{report_id}/draft-next-plan` reads the finished report, latest review, EMG/intent overview, and source plan, calls the same App training-planner relay path when configured, then creates an AI training draft only. The accepted draft becomes a new normal training plan and still requires current-version `sync-to-device` plus `m33_accepted` before a session record can start.
- BLE message endpoints prepare and audit structured App-to-M33 messages without sending motor commands: `POST /devices/{device_id}/ble/messages`, `GET /devices/{device_id}/ble/messages`, and `POST /devices/{device_id}/ble/messages/{message_id}/ack`. The allowed message types are App hello, device status request, training plan push, training session start/progress/pause/stop request, and diagnostic snapshot request. Payloads and ACKs reject motor/CAN/raw motion/M33 override/emergency-stop release fields. For the old Android transport, `training_plan_push` generates a newline JSON `memory` frame, `training_session_start_request` generates `execute_memory`, pause/stop generate `stop_memory` / `stop`, and unsupported status-like messages remain non-sendable.
- Platform sync summarizes training plans, sessions, reports, report reviews, AI training drafts, EMG summaries, and M33 decisions as evidence-only resource counts.
- `GET /safety-audit` returns rehab-arm App audit events for the user and bound M33 device identities so M33 accept/reject decisions are visible to the phone workflow.
- `GET /me.care_timeline` is the phone continuity/calendar source and includes `training_plan`, `training_session`, `training_report`, `ai_training_draft`, and offline evidence items. The phone calendar may highlight any persisted rehab activity, while completed training counts must still come only from `training_session` records so planning evidence is not confused with performed exercise.
