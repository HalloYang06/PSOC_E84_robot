# Runner Implementation Status

This note tracks the first-version Runner against the platform docs.

## Implemented

- Runner registration
- Heartbeat loop
- Runner relay inbox polling
- Next-task polling
- Per-task workspace creation
- Local task log writing
- Allowlisted command execution
- Allowlisted serial/USB command execution behind `ALLOW_HARDWARE_ACCESS=true`
- Allowlisted read-only Git preflight execution through `git.preflight`
- Task log reporting
- Task result reporting
- Hardware access flag in config

## Present but intentionally limited

- `MAX_CONCURRENT_TASKS` is configured but not yet used for real parallel execution
- workspace cleanup exists as an explicit helper, but the main loop keeps workspaces for debugging
- task execution only accepts a tiny command allowlist
- hardware execution only accepts `serial.usb.scan` and `serial.write`
- Git relay execution only accepts `git.preflight`; it checks local Git/credential readiness and never mutates repositories
- fetch-next-task falls back safely if the endpoint is unavailable

## Not implemented yet

- arbitrary shell execution
- arbitrary hardware control
- direct Git clone/pull/push/reset/revert execution
- automatic retry orchestration
- advanced scheduling across multiple tasks
- workspace garbage collection policy

## Verification notes

This status reflects the current source under `apps/runner/runner/`:

- `runner/main.py`
- `runner/client/platform.py`
- `runner/executor/limited.py`
- `runner/hardware/serial_tools.py`
- `runner/git_tools.py`
- `runner/config.py`
- `runner/workspace/manager.py`
- `runner/logs/collector.py`

The implementation is intentionally conservative for the first MVP and is meant to match the platform's safety and human-confirmation rules.

## Productization checks to keep green

- a runner still maps to one machine and one local workspace root
- the platform can describe more than one computer node in a project
- different AI providers can be assigned to different workstations inside one project
- Git actions remain visible as explicit sync / rollback records
- Git sync / rollback registration can enqueue read-only Runner preflight before human-approved execution
- no test or doc should imply that the Runner itself performs cross-machine scheduling
- Runner write endpoints use `X-Runner-Id`; app-user bearer tokens are not used by the local runner process
