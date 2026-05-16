# NPC Workbench Structure Contract

This document is the product contract for continuing platform self-development without breaking the accepted NPC Workbench.

## Core Principle

The main project page manages resources. The NPC Workbench executes collaboration.

The user should never need to know a desktop thread id. Thread binding belongs in the main page NPC management flow, where the platform scans desktop threads and the user selects by thread name. The NPC Workbench may show binding status and link back to management, but it must not become a thread-id form.

## Functional Structure

| Surface | User job | Existing/original function to preserve | New capability allowed here | Must not happen |
| --- | --- | --- | --- | --- |
| Main project page / NPC management | Create, configure, bind, and govern NPC seats | Create NPC, edit role, choose workstation, scan computer threads, select a scanned thread by name | Show thread health, automation policy, Skill loadout, knowledge path, Git/computer governance | Do not ask normal users to paste thread ids; do not run collaboration dialogs here as the main execution surface. |
| NPC Workbench | Use NPCs as collaborators | Multi-NPC tiles, each tile has dialog stream and composer, role colors, structured cards, review controls, long receipt drawers | Desktop question/minimal receipt sync, scoped evidence preview, closeout actions, professional-view links, autonomous dispatch receipts | Do not replace the dialog with setup panels; do not move thread binding forms here; do not remove the composer. |
| Data Factory | Work with data evidence | Navigate from a task/message evidence chain | Dataset manifest, samples, labels, QA, export status, ingestion next action | Do not become a generic link wall or clone external labeling tools. |
| AI Lab | Compare experiments and simulations | Navigate from the same task/evidence chain | Scenario runs, metrics, traces, approval boundaries, replayable evidence | Do not make decorative dashboards without executable next actions. |
| Robotics Field | Inspect device/robot state safely | Navigate from the same task/evidence chain | Read-only robot/board/ROS/topic/model/waveform views, hardware safety gates | Do not bypass strong review for hardware, deployment, motion, firmware, publish/service/action writes. |
| Observability | Understand platform execution health | Show dispatch chain, receipts, pending review/closeout, API/web instance health | Retry/resync/nudge entry points that return users to the correct NPC context | Do not hide current blockers inside historical noise. |

## Message Stream Structure

NPC Workbench messages are the canonical visible execution timeline. All message-like information should stay in the stream and be visually typed:

| Message kind | User-facing label style | Placement |
| --- | --- | --- |
| Human command | Human/user color | Message stream, with the original command visible. |
| Current NPC response | Current-NPC color | Message stream, with final receipts collapsed by default when long. |
| Same-workstation NPC | Same-workstation color | Message stream, with peer dispatch/receipt cards. |
| Cross-workstation NPC | Cross-workstation color | Message stream, routed through the responsible lead when needed. |
| Desktop sync | Thread/sync color | Message stream as "desktop question" or "minimal receipt"; no local file/session names. |
| System/audit/review | System/review color | Message stream as structured cards with approve/reject or closeout actions. |

Long text must use an explicit drawer or expand action. The short stream should show who, status, summary, evidence chips, and next actions.

## Original Core That Must Stay

| Area | Must stay | Why |
| --- | --- | --- |
| Left NPC index | Humans, computers, NPC list, open/close tile controls | Users need fast multi-NPC switching. |
| Tile layout | Multiple NPC conversation tiles can stay open side by side | This is the main collaboration surface. |
| NPC dialog | Each NPC tile has its own message stream and input box | Users dispatch, review, and inspect NPC work here. |
| Message colors | Human, current NPC, same-workstation NPC, cross-workstation NPC, sync/system/receipt messages use distinct labels/colors | Users must see who said what without reading raw metadata. |
| Structured cards | Boundary cards, tasks, approvals, peer dispatches, receipts, evidence, risk cards render inside the message stream | Different message types stay in one dialog, visibly typed. |
| Long text drawer | Long final receipts and detailed bodies collapse behind “查看回执 / 展开 / 收起” | The dialog stays readable without losing audit detail. |
| Review controls | Pending-review messages show approve/reject controls in place | Human approval happens in context. |
| Minimal receipts | Ack/progress/final receipts appear in the same dialog | Users can watch execution without leaving the workbench. |
| Desktop process pointer | The workbench can say the full process is in the desktop thread and link to it | Platform indexes the process; desktop app remains the full execution surface. |

## Newer Capabilities That Fit The Dialog

These are good additions only if they preserve the original structure above.

| Capability | Correct placement | Rules |
| --- | --- | --- |
| Desktop question/minimal receipt sync | Message stream | Show as typed events with labels such as “桌面提问 / 最小回执”; do not expose session files or JSONL. |
| Evidence preview | Inside a message, near the receipt/card that owns the artifact | Preview only evidence registered to the current task/source message. Keep long content scrollable or drawer-like. |
| Professional-view links | Inside relevant messages as small action chips | Links point to Data Factory / AI Lab / Robotics for the same task evidence chain. Do not turn the dialog into those pages. |
| Closeout actions | On waiting/stale messages | “催办 / 延长等待 / 重新同步 / 手动收口” is okay; keep the command status auditable. |
| Autonomous dispatch status | Structured card or receipt in the stream | Show Boss/NPC-to-NPC dispatch progress in the same typed-message style. |

## Belongs On Main Page NPC Management

These should not live as editable forms inside the NPC Workbench dialog.

| Resource/Governance | Main-page behavior |
| --- | --- |
| Create NPC | Main page NPC management. |
| Assign workstation / responsibility | Main page NPC management. |
| Bind desktop thread | Main page NPC management: scan computer threads, show thread names, user selects one. |
| Rebind desktop thread | Same scanned-thread selector; no manual thread id for normal users. |
| Generate onboarding pack | Main page NPC management after a thread is selected. |
| Skill loadout | Main page NPC management / Skill area. |
| Knowledge paths | Main page NPC management / repo governance. |
| Computer / Runner pairing | Main page computer management. |
| Scan desktop threads | Main page computer management. |
| Automation default policy | Main page governance; workbench may show on/off state and allow lightweight toggle only if already bound. |

## Belongs In Other Same-Level Workbenches

These workbenches are first-class peers, not replacements for the NPC Workbench.

| Workbench | Job |
| --- | --- |
| Data Factory | Dataset manifests, samples, labeling/QA, evidence ingestion, data task next actions. |
| AI Lab | Experiments, model/simulation runs, approval boundaries, result comparison, replayable evidence. |
| Robotics Field | Read-only robot state, model/topic/waveform views, ROS/Linux/runner planning, hardware safety gates. |
| Observability | Dispatch chain, minimal receipts, pending closeout, anomalies, API/web instance health. |

All of them should read/write the same project objects: task, dispatch, collaboration message, receipt, artifact, audit. They should not create isolated dashboards.

## User-Facing Rules

1. Do not show raw thread ids as something the user must type.
2. Do not expose adapter, bridge, session JSONL, local prompt file, workstation-inbox paths, or local drive paths.
3. Do not replace the NPC dialog with a setup panel.
4. Do not remove message colors, role labels, structured cards, or long-text drawers.
5. Do not hide failures; convert them into understandable actions.
6. Hardware, deployment, motion, firmware, and real ROS write actions remain strong-review. Read-only planning can proceed.
7. External GitHub/open-source material should become internal platform capability, not a link wall.

## Acceptance Checks Before Future NPC Workbench Changes

Any change touching the NPC Workbench must prove:

1. Opening multiple NPC tiles still shows independent dialogs.
2. Each open NPC tile still has a visible message stream.
3. Each open NPC tile still has an input box.
4. The legend or role labels still distinguish human/current NPC/same-workstation/cross-workstation/system or sync messages.
5. Long messages still expose a drawer/open action.
6. Pending-review messages still show approve/reject in context.
7. Evidence preview, if present, is scoped to the message/task evidence chain.
8. No normal-user surface asks for a desktop thread id.
9. Thread binding entry points route to main page NPC management or computer scan.

## Next Implementation Order

1. Repair any accidental NPC Workbench structure drift.
2. Make the validation script enforce the acceptance checks above.
3. Verify the main page NPC management still supports scanned-thread selection by thread name.
4. Only then continue same-level workbench productization.
