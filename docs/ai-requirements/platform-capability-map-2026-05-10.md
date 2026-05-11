# Platform Capability Map - 2026-05-10

## Product Scope

The platform is not YueSpeak-only. YueSpeak is a software validation scene. Robotics and mechanical-arm development are the broader target scene: app, ROS/Linux, VLA/perception, embedded firmware, hardware lab, and QA/safety may run on different computers with different owners.

The stable structure remains:

```text
Project -> Workstation -> NPC -> Thread
Company -> Department -> Employee -> Tool/Computer thread
```

## Page Ownership

### Project Main Page: `/2d-upgrade`

Owns resource governance. Keep creation and long-lived configuration here:

- project Boss NPC and thread binding
- computers / runners / online status / duplicate service warning
- logical workstations and workstation leads
- NPC identities, roles, permissions, memory paths, skill loadouts
- GitHub skill import and skill library
- GitHub repo-relative knowledge paths
- runner capabilities such as `ros`, `embedded-build`, `serial-log`, `vla-eval`, `browser`
- review policies, including NPC-pair免审 and high-risk overrides
- project operating contract and robotics profile

### Collaboration Workbench: `/workbench`

Owns execution, not resource creation:

- open people/NPC/thread tiles
- user-to-NPC prompt and Boss dispatch
- NPC-to-NPC dispatch
- same-workstation collaboration
- cross-workstation via target workstation lead
- pending review with concrete body drawer
- approve / reject / approve-and-remember-pair
- receipts, agent ack/progress/done/reject
- concise event timeline, with raw thread output hidden behind drawers

### Future Robotics Workbenches

These should reuse main-page resources instead of recreating them:

- Hardware AI simulation workbench: simulation evidence, scenario replay, safety case.
- PID/debug workbench: parameter proposal, review gate, waveform/log evidence.
- Lab/experiment workbench: preflight, human operator, evidence upload, rollback record.

## Button And Action Cleanup Rules

Do not add one visible button per backend feature. Group actions by the user's next decision:

- Dispatch: choose target, send task.
- Review: approve, reject, approve and remember this pair.
- Relationship: show one compact `需审 / 免审中` switch for the current NPC -> target NPC pair.
- Queue: accept, complete, reject.
- Thread: bind, launch pack, automation toggle.
- Raw details: use a drawer, not a permanent text block.

Avoid duplicate actions in both main page and workbench. If an action changes resources, it belongs on the main page. If it advances a collaboration message, it belongs in workbench.

## Robotics-Specific Requirements

Boss NPC must recommend workstations based on the prompt:

- App/UI workstation for operator app, telemetry, cloud/API.
- ROS/Linux workstation for packages, launch files, services, rosbag/logs.
- VLA/perception workstation for camera, dataset, model eval, inference.
- Embedded/hardware workstation for firmware review, serial/CAN logs, preflight.
- QA/safety workstation for simulation, safety cases, experiment records.

Each workstation should have:

- required runner capabilities
- repo-relative knowledge paths
- allowed read/write paths
- risk policy
- lead NPC
- default review policy

High-risk hardware actions must force review even when a pair is marked免审. Examples: firmware flashing, serial writes, PID changes, actuator movement, homing, power switching, calibration, deleting device logs.

## Current Gap Found During YueSpeak Validation

The workbench can show relation-level免审, but there are still stale pending_review rows whose route text says "审核：免". This is a state consistency bug. The backend must treat review decision as the single source of truth and never persist `pending_review` when the resolved decision is skip.

Also found: multiple old uvicorn reload processes can survive and serve stale code. The main page needs a runner/service instance health view before robotics multi-computer work, otherwise the user cannot tell which computer or service is actually active.

## Near-Term Acceptance

1. Boss -> Backend Data default dispatch enters pending review.
2. User can approve with concrete body visible.
3. User can approve and remember the NPC pair.
4. Same pair shows `免审中`.
5. Same pair next dispatch is queued, not pending_review.
6. User can turn免审 off and the next dispatch returns to pending review.
7. Hardware-touch/H3/H4 messages still require review even if the pair is免审.
