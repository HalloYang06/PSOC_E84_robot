# Project Operating Contract

## Purpose

This is the default contract every project Boss NPC and execution NPC must follow before autonomous work starts. The platform structure is:

`project -> workstation -> NPC -> thread`

The thread can be Codex, Claude Code, or another runner, but the NPC identity and knowledge paths stay stable.

## Required Project Setup

Before Boss NPC dispatches real work:

1. The user creates or chooses a Boss NPC inside the project.
2. The Boss NPC has a real execution thread id registered in the platform.
3. Each workstream has a workstation, at least one NPC, and the NPC has a thread id or an explicit "not ready" status.
4. Each NPC has a stable knowledge memory file under `docs/ai-handoffs/npc-memory/`.
5. The repository structure below is visible to every thread through GitHub repo + branch + relative paths.

If any item is missing, Boss NPC may generate a plan, but must not claim the project is ready for autonomous execution.

## Local Workspace Layout

Each computer chooses its own absolute clone path. Do not hardcode another computer's local path in tasks.

Required local shape, relative to each clone root:

```text
.
├── apps/
│   ├── api/                 # Backend API, database modules, API tests
│   ├── web/                 # User-facing web app and workbench UI
│   └── runner/              # Local runner / thread bridge logic
├── scripts/                 # Validation, watcher, bridge, and maintenance scripts
├── docs/
│   ├── ai-handoffs/         # Durable AI handoffs, operating contracts, inbox, NPC memory
│   │   ├── project-operating-contract.md
│   │   ├── inbox/           # Project and NPC handoff packets
│   │   └── npc-memory/      # One stable memory file per NPC identity
│   ├── ai-requirements/     # Product requirements, acceptance plans, design records
│   └── user-guides/         # User-facing instructions
└── artifacts/
    └── page-audit-*/        # Browser screenshots and validation reports
```

NPCs may add subfolders only when they have a clear owner and purpose. Prefer extending the folders above before creating new top-level directories.

## GitHub Repository Layout

GitHub is the shared source of truth. All tasks must use repository-relative paths.

Required conventions:

1. Use repo-relative paths in messages, handoffs, and review notes.
2. Do not mention local absolute paths unless reporting where a screenshot or local artifact was written.
3. Branches are owned by humans unless the user explicitly lets an NPC create one.
4. Every NPC response that changes code must say:
   - changed files
   - validation run
   - residual risk
   - next handoff target
5. If multiple NPCs work in parallel, they must declare disjoint write scopes before editing.

## Knowledge Layout

Project-level knowledge:

- Contract: `docs/ai-handoffs/project-operating-contract.md`
- Requirements/design: `docs/ai-requirements/`
- Cross-NPC handoffs: `docs/ai-handoffs/inbox/`
- Long-lived NPC memory: `docs/ai-handoffs/npc-memory/<npc-slug>.md`

NPC memory rules:

1. A memory file belongs to the NPC identity, not to the current thread.
2. Switching from Claude Code to Codex does not create a new identity.
3. Each NPC should keep only verified facts, decisions, constraints, and recurring pitfalls in memory.
4. Temporary logs belong in `artifacts/` or message receipts, not permanent memory.

## Skill Contract

Skills are referenced by stable names, not by one computer's installed folder path.

Recommended baseline:

- Boss NPC: `requirements-ledger`, `project-planning`, `acceptance-criteria`, `boss-dispatch-loop`, `handoff-path-output`
- Frontend NPC: `frontend`, `browser-validation`, `ui-review`
- Backend NPC: `backend-api`, `database`, `contract-test`
- QA NPC: `acceptance-test`, `browser-validation`, `risk-check`
- Runner NPC: `thread-bridge`, `automation-switch`, `receipt-normalization`
- Robotics App NPC: `mobile-app`, `api-contract`, `telemetry-ui`, `browser-validation`
- ROS/Linux NPC: `ros`, `linux-service`, `systemd`, `launch-file`, `bag-log-analysis`
- VLA/ML NPC: `vision-language-action`, `dataset-curation`, `model-eval`, `safety-case`
- Hardware NPC: `embedded-build`, `serial-log`, `firmware-review`, `hardware-preflight`

When Boss NPC sees a missing capability, it should recommend a skill name and explain why the project needs it. The user chooses whether to install or bind it.

## Multi-Computer / Robotics Project Profile

YueSpeak is one validation scene. The same platform must also support robotics and mechanical-arm projects where execution is split across multiple computers and physical devices.

Boss NPC should model these workstations when the project mentions robot, ROS, VLA, Linux, firmware, motion control, sensors, or mechanical arm:

- Product/App workstation: mobile/web app, operator UI, telemetry display, cloud/API contracts.
- ROS workstation: packages, launch files, topics/services/actions, rosbag analysis, simulation bridge.
- Linux/Edge workstation: drivers, systemd services, deployment scripts, permissions, logs on edge computers.
- VLA/Perception workstation: camera pipeline, dataset notes, model eval, inference service, safety constraints.
- Embedded/Hardware workstation: firmware build review, serial/CAN log analysis, preflight checklist, device records.
- QA/Safety workstation: acceptance tests, simulation results, hardware risk checks, rollback and experiment evidence.

Each workstation must declare:

```text
runner_capabilities:
repo_relative_knowledge_paths:
allowed_read_paths:
allowed_write_paths:
hardware_touch: true/false
risk_level: H0/H1/H2/H3/H4
human_review_policy:
```

Runner scheduling must use capability tags, not only "online" status. Example capability tags:

```text
codex
claude-code
linux-shell
ros
ros2
gazebo
isaac-sim
serial-log
embedded-build
android-build
ios-build
vla-eval
browser
git
```

Knowledge must stay GitHub repo-relative. Local paths differ by computer, especially when one computer owns the ROS workspace and another owns the app or firmware workspace.

## Hardware Safety Rules

For robotics and embedded projects, the platform may help plan, review, simulate, build, parse logs, and produce checklists. It must not silently execute high-risk hardware actions.

Always require human review and an experiment record for:

- firmware flashing or bootloader changes
- serial/CAN/GPIO/network commands that alter real hardware state
- PID, current, velocity, torque, limit, calibration, or safety parameter changes
- mechanical-arm, actuator, motor, gripper, wheel, or servo movement
- power switching, homing, reset, zeroing, calibration, or self-test that may move hardware
- deleting or overwriting device logs, calibration files, or rollback artifacts

High-risk dispatches should include:

```text
Target device:
Risk level:
Simulation evidence:
Preflight checklist:
Expected physical effect:
Rollback plan:
Human operator:
Evidence to upload:
```

Same-workstation NPCs can be trusted gradually, but hardware-touch and H3/H4 actions still override pair-level免审 and must stop for human approval.

## Boss NPC Workflow

Boss NPC owns planning and routing, not hidden execution.

1. Intake: turn the user's prompt into objectives, non-goals, acceptance criteria, risks, and expected deliverables.
2. Structure: map the work to repository folders, GitHub paths, workstations, NPC roles, and required skills.
3. Readiness: check Boss thread, target NPC threads, automation switches, and missing skill/knowledge paths.
4. Dispatch: send concise tasks to ready NPCs only.
5. Collect: read acknowledgements, progress receipts, final replies, and raw drawer details when needed.
6. Re-route: send follow-up work to the right NPC when a dependency is discovered.
7. Verify: require tests, build, and browser/user validation for user-facing changes.
8. Close: summarize what is true, what changed, screenshots/reports, and what remains blocked.

## Message Contract

Workbench chat should stay concise. Long execution details belong behind raw drawers or in handoff docs.

Dispatch body must include:

```text
Goal:
Scope:
Repo paths:
Knowledge paths:
Required skills:
Acceptance checks:
Return receipt:
```

NPC receipt must include:

```text
Understood:
Changed:
Validated:
Blocked:
Next:
```

## User Review Rules

The platform should interrupt for human review when work includes:

- destructive file operations
- production publish/deploy
- account, billing, or credential changes
- hardware, serial, GPIO, firmware flashing, or physical movement
- unclear scope with high blast radius

Boss NPC must mark these as blockers until the user approves the specific action.

## Product Rule

The platform shows coordination. Codex, Claude Code, and runner threads do the real work. Do not fake execution in the UI.

The platform must not become a replacement chat surface for Codex or Claude Code. Long reasoning, command output, implementation logs, and tool-heavy work stay inside the bound Codex / Claude Code thread. The platform stores only dispatch summaries, minimum acknowledgements, human-review decisions, final results, and links or indexes back to the responsible resource.
