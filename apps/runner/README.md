# Runner

`apps/runner` is the first-version Runner implementation for the AI collaboration platform.

It is a lightweight local worker that can:

- register itself with the platform
- send periodic heartbeats
- poll the Runner relay inbox
- poll for the next task
- create a per-task workspace
- execute only a small allowlist of commands
- execute allowlisted serial/USB hardware commands when hardware access is enabled
- execute allowlisted read-only Git preflight checks
- write local logs
- report task logs and task results back to the platform

## What it currently supports

The current implementation in `runner/main.py` follows this flow:

1. load configuration from environment variables
2. ensure local work directories exist
3. register the runner with the platform
4. send heartbeats on a fixed interval
5. poll the Runner relay inbox for allowlisted platform commands
6. fetch the next task from the platform
7. prepare a task workspace
8. execute allowlisted commands from `task["commands"]`
9. post task logs and a final task result

This is intentionally narrow for the first version. It is not a general-purpose job runner and it does not execute arbitrary shell commands.

## Configuration

Set these environment variables before starting the runner:

- `RUNNER_ID` - runner identifier, default: `runner-local`
- `RUNNER_NAME` - display name, default: same as `RUNNER_ID`
- `PLATFORM_API_URL` - platform API base URL, default: `http://localhost:8000`
- `RUNNER_TOKEN` - optional runner registration/pairing token, default: `change-me`
- `RUNNER_WORKDIR` - local workspace root, default: `./artifacts/runner-workspace`
- `ALLOW_HARDWARE_ACCESS` - `true` or `false`, default: `false`
- `MAX_CONCURRENT_TASKS` - reserved configuration for later use, default: `1`
- `HEARTBEAT_SECONDS` - heartbeat interval, default: `15`
- `POLL_SECONDS` - task polling interval, default: `10`

## Execution model

Each fetched task is handled independently:

- workspace root: `RUNNER_WORKDIR/tasks/<task_id>`
- local logs: `RUNNER_WORKDIR/logs/<task_id>/runner.log`
- artifacts: `RUNNER_WORKDIR/artifacts/<task_id>`

The workspace is created on demand and kept by default for debugging. Cleanup is intentionally conservative in this first version.

## Command allowlist

The limited executor currently allows only:

- `echo ...`
- `git --version`
- `python --version`
- `node --version`

Any other command is rejected by design.

## Serial TV hardware commands

When `ALLOW_HARDWARE_ACCESS=true`, the runner can handle the serial TV commands sent from the farm's main-house TV:

- `serial.usb.scan` - scans local serial ports and USB devices, then completes the runner relay message with a JSON result.
- `serial.write` - writes a bounded payload to one local serial port and returns a small readback preview.

The runner still does not execute arbitrary shell commands for hardware work. These commands are parsed from the relay message body as JSON and must match the allowlist above.

The default data protocol exposed in the UI is `AICSV/1`:

- `@xy,<x>,<y>` for two-axis points.
- `@sample,<t>,<ch1>,<ch2>...` for timeline samples.
- `@cmd,<name>,key=value;key=value` for small command frames.
- Plain numeric CSV like `12.5,33.1` is treated as x/y compatibility input.

Install `pyserial` on the target computer if `serial.write` should open real ports. Without `pyserial`, scans can still use OS fallbacks where available, and writes return a clear failure note instead of pretending to succeed.

## Git preflight commands

The runner can also handle `git.preflight` relay messages from the project Git panel.

This is intentionally read-only:

- runs `git --version`
- checks whether the configured credential source is available, such as a Runner environment variable or SSH Agent
- reports repository URL, branch, local-path policy, and human-review boundary back to the platform
- refuses secret-looking credential refs and refuses non-dry-run payloads
- never runs clone, pull, push, reset, revert, delete, or release commands

The platform should use this first before asking a human to approve any real Git operation. Each computer still chooses its own local clone path; one computer's absolute path must not be sent as the source of truth for another machine.

## Platform endpoints used

The runner client currently calls these API routes:

- `POST /api/runners/register`
- `POST /api/runners/heartbeat`
- `GET /api/runners/{runner_id}/inbox`
- `POST /api/runners/{runner_id}/messages/{message_id}/ack`
- `POST /api/runners/{runner_id}/messages/{message_id}/complete`
- `GET /api/runners/{runner_id}/next-task`
- `POST /api/tasks/{task_id}/logs`
- `POST /api/tasks/{task_id}/result`

If the platform does not yet expose the task-fetch endpoint, the runner treats it as unavailable and keeps polling.

## Current limitations

- no parallel task execution yet
- no arbitrary command execution
- no arbitrary hardware control; only `serial.usb.scan` and `serial.write` are enabled behind `ALLOW_HARDWARE_ACCESS=true`
- no direct Git mutation; only `git.preflight` read-only checks are enabled
- no automatic workspace cleanup
- no sophisticated retry or backoff policy

## Multi-computer collaboration model

The platform treats each physical machine as a `computer_node`, each AI vendor/persona as an `ai_provider`, and each thread assignment as a `thread_workstation`.

For productized use, this means:

- `Computer 1 + Codex + UI workstation` can own interface and coordination work
- `Computer 2 + Claude + robot workstation` can own robot strategy or lower-level execution planning
- Git remains the source of truth for code changes, branches, review, and rollback
- a Runner is still local to one machine, but a project can describe many machines and many AI workstations
- the platform now exposes explicit Runner bind/unbind routes for project computer nodes, so ops can move bindings without editing JSON by hand

The platform also exposes CRUD routes for the same three project-scoped entity types, plus explicit Runner bind/unbind routes for project computer nodes, so the control plane can edit the collaboration topology instead of only rendering it.

This Runner does not schedule across machines by itself. It only executes the task assigned to the local machine and reports logs/results back to the platform.

That boundary is intentional: productized cross-machine orchestration belongs to the platform layer, while Runner stays local and deterministic.

## Acceptance checklist

Use this checklist when verifying a productized setup:

- the project can persist `computer_nodes`, `ai_providers`, and `thread_workstations`
- the project can create, update, and delete `computer_nodes`, `ai_providers`, and `thread_workstations`
- the project can round-trip a robot collaboration layout without losing mappings
- session authentication works for write flows that should be human-controlled
- Git sync and rollback actions are recorded in project activity logs
- Git sync and rollback registration can enqueue runner-side `git.preflight` messages before any real Git execution
- the Runner still executes only its command allowlist
- a task workspace is created under a task-scoped local root and can be cleaned up explicitly
- a Runner can be bound to one or more project computer nodes through explicit API routes

## What is usable today

- You can already describe a multi-computer project in the platform model.
- You can already create, update, delete, and round-trip a multi-computer collaboration config that maps computer nodes, AI providers, and workstations.
- You can already see which projects and computer nodes are bound to a Runner.
- You can already bind and unbind a Runner from project computer nodes through explicit API routes.
- You can already log a project's Git sync and rollback activity.
- You can already let bound runners perform a read-only Git preflight for sync and rollback requests.
- You can already run a local Runner that creates a task workspace, writes logs, and executes only a tiny command allowlist.
- Remote cross-machine scheduling is still a platform-level roadmap item, not a Runner feature.

## Local entry point

Run the package with:

```bash
python -m runner
```

## Related files

- [runner/main.py](./runner/main.py)
- [runner/config.py](./runner/config.py)
- [runner/client/platform.py](./runner/client/platform.py)
- [runner/executor/limited.py](./runner/executor/limited.py)
- [runner/workspace/manager.py](./runner/workspace/manager.py)
- [runner/logs/collector.py](./runner/logs/collector.py)
