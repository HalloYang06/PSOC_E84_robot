# API Tests

This directory contains the acceptance tests for the AI collaboration platform.

## What these tests cover

- session authentication and `GET /api/auth/me`
- write access guardrails for human-controlled flows
- shared permission contract/regression coverage for core write routes
- unified response shapes and pagination contracts
- multi-computer / multi-AI / multi-thread collaboration configuration round-trips
- direct CRUD for project-scoped `computer_nodes`, `ai_providers`, and `thread_workstations`
- thread workstations now preserve AI employee metadata such as `responsibility`, `model`, `permission_level`, `read_paths`, and `write_paths`
- project-level computer node connection details such as `connection_kind`, `workspace_root`, `git_root`, `read_paths`, and `write_paths`
- Runner binding visibility across one or more projects
- explicit Runner bind/unbind routes for project computer nodes
- Runner workspace aggregation and documented command allowlist
- knowledge library membership filtering and promoted requirement listing
- merge-readiness summaries for Git branches and blocker aggregation
- project Git sync and rollback activity logging

## How to run

From `D:\ai-collab-product\apps\api`:

```powershell
python -m pytest tests -q
```

## AI collaboration proof run

If you want the shortest proof that the platform collaboration loop is still alive, run:

```powershell
pwsh ..\..\scripts\verify-ai-collab-loop.ps1
```

This proof run executes four high-signal tests:

- `tests/test_runner_relay.py::test_runner_relay_command_round_trip`
  - proves `runner command -> ack -> complete -> task status` still works
- `tests/test_runner_relay.py::test_runner_relay_command_accepts_structured_dispatch_id_without_legacy_body_hint`
  - proves dispatch bridging no longer depends on the legacy `Dispatch ID:` body line
- `tests/test_requirement_autonomy_flow.py::test_requirement_autonomy_sweep_dispatches_and_creates_follow_up_for_platform_templates`
  - proves platform autonomy sweep can dispatch a requirement and auto-create the next follow-up dispatch
- `tests/test_requirement_autonomy_flow.py::test_runner_completion_backfills_requirement_final_reply_and_follow_up`
  - proves a runner completion can drive `minimal ack/final reply/follow-up requirement` in one chain

## Current productized boundary

- Projects can now persist a collaboration topology that describes computer nodes, AI providers, and thread workstations.
- The collaboration API exposes CRUD routes for those same three entity types, so the control plane can edit the topology instead of only rendering it.
- Project updates can also carry per-node connection metadata inside `collaboration_config`, which is preserved on the project read model even when the inventory layer only needs the normalized node identity and runner binding.
- Thread workstation AI employee semantics currently round-trip through workstation `metadata` / `extra_data`, so fields like `responsibility`, `model`, `permission_level`, and path access survive create/update even before they become dedicated columns.
- The current task/workstation readiness check is a local heuristic built from the Git workspace read model, not a dedicated server endpoint. Matching is intentionally simple: a workstation is considered a better fit when its `agent_id` matches the task `assignee_agent_id`, it is active, its permission level is high enough, and it has both read and write paths configured.
- Runner tests still verify the local execution boundary. A Runner can be bound to one or more project computer nodes through explicit API routes, but it still does not orchestrate other machines by itself.
- The current binding model is writable through explicit bind/unbind API routes, while project collaboration inventory remains the underlying source of truth.
- Git sync and rollback are tracked as project activity, but the actual repository action remains a platform-level workflow, not a direct shell executor inside the API.

## Notes

- The productized path is session-token based, so tests prefer `POST /api/auth/session` where possible.
- Test-only startup conveniences such as auto-create and demo seeding are now enabled explicitly through `tests/conftest.py`, not through application defaults.
- Runner workspace tests prove the local execution boundary only: one task maps to one workspace root, and arbitrary shell execution stays blocked by the allowlist.
- Runner workspace aggregation is covered by the binding tests, which verify the read model stays aligned with project collaboration inventory after bind and unbind operations.
- The Runner binding contract test now verifies the explicit bind/unbind API directly, and it checks that the workspace read model returns to an empty state after unbinding.
- The collaboration inventory regression test now checks that connection/workspace/git-root/read-write-path details survive a project config round-trip while the normalized inventory still syncs correctly.
- The thread workstation metadata regression test now checks that responsibility/model/permission_level/read_paths/write_paths survive a workstation create/update round-trip through `metadata`.
- The shared permission audit tests now cover the remaining write endpoints that were easy to miss in earlier rounds, so core POST/PATCH/DELETE routes get a quicker regression signal.
- The knowledge regression test now validates project membership filtering and promoted requirement visibility through `/api/knowledge`.
- The merge-readiness regression test now checks blocker aggregation and branch state without depending on volatile activity counters.
