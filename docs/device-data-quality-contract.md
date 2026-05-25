# Device Data Quality Contract

This contract keeps the platform generic. The device data workbench must support
robotics, embedded boards, sensors, cameras, audio, logs, and other capture
sources without becoming specific to the rehabilitation arm project.

## Purpose

The platform may receive manifests, low-frequency previews, keyframes, motor
telemetry, sensor telemetry, safety summaries, and derived quality indexes.
These records are data assets for debugging, labeling, chart experiments, model
training, and evidence review.

They are not motion permission.

## Current Schema

`device_recording_quality_index_v1` is the generic quality index used by the
backend. It answers:

- whether a capture session is ready for annotation or export;
- which sessions were accepted;
- which warnings or blocking reasons should be shown to the user;
- which adapter produced the source data.

The rehabilitation arm sync endpoint currently produces this generic index from
manifest uploads. A session may include:

- `summary`: stream counts, moving joint count, motor entry counts, and safety
  state statistics;
- `quality_report`: the upstream data quality gate result, including `ok`,
  `errors`, `warnings`, and `criteria`.

When `quality_report` is present, the platform treats `quality_report.ok=false`
as a blocking condition for annotation/export readiness and surfaces its errors
as blocking reasons. When only `summary` is present, the platform derives a best
effort quality index from the summary.

The index may include `adapter: "rehab_arm_sync_v1"` for traceability, but UI
copy should say "device data quality" instead of "rehab arm quality".

## Safety Boundary

The server and web UI must never send:

- raw CAN frames;
- motor current, torque, velocity, or raw position commands;
- M33 override commands;
- emergency-stop bypasses;
- direct real-hardware motion commands.

The server may send:

- high-level task requests;
- data collection requests;
- annotation tasks;
- chart experiment requests;
- configuration suggestions that still require the proper local safety gate;
- VLA task drafts that must be converted by the local robot stack before motion.

For wearable or safety-critical devices, the local controller remains the final
safety authority. For the rehabilitation arm adapter, that authority is M33.

## Workbench Behavior

The device data workbench should show:

- latest device status and online/offline state;
- latest low-frequency camera keyframe or preview image when available;
- latest motor/sensor/safety telemetry as read-only data;
- capture sessions and their quality index;
- annotation and export actions when `annotation_ready` is true;
- warnings when data is incomplete, static, or missing expected streams.

The workbench should not expose internal words such as adapter, bridge, raw UUID,
session JSONL, or local path in normal user-facing copy.

## Validation Notes

Cloud smoke validation on 2026-05-25:

- uploaded an offline sample manifest with `quality_report` through
  `/api/rehab-arm/v1`;
- cloud dashboard returned `annotation_ready=true` for device
  `nanopi-quality-demo`;
- latest session returned `quality_report_ok=true` and preserved the source
  quality criteria;
- returned `control_boundary=data_quality_only_not_motion_permission`.

This validates the data-readiness path only. It does not validate camera
streaming, VLA planning, ROS execution, CAN writes, M33 control, or any real
hardware motion path.
