# Cloud Deployment Runner P0 Checklist

Last verified: 2026-05-17

## Cloud Services

Production cloud endpoints:

- Web: `http://106.55.62.122:3001`
- API: `http://106.55.62.122:8011`

Restart on the Ubuntu server:

```bash
cd ~/apps/ai-collab
RESTART=1 scripts/start-cloud-prod.sh
```

Expected health checks:

```bash
curl http://127.0.0.1:8011/api/health
curl http://127.0.0.1:3001/api/proxy/health
ss -lntp | grep -E '3001|8011'
```

The public Web port is `3001`; runner API calls must go to `8011`.
The health payload should include `deployment.build_sha`, `deployment.build_ref`, and `deployment.build_time`.
If `scripts/check_web_api_alignment.py` reports `deployment fingerprint missing`, the server is alive but still running an old build.

## P0 Validation

Run from the development machine:

```powershell
python scripts/check_web_api_alignment.py --web-base http://106.55.62.122:3001 --api-base http://106.55.62.122:8011 --project-id fe9bd342-f5ef-4afe-9c73-e7caa2ed17dd
python scripts/validate-cross-platform-runner-onboarding.py
python scripts/validate-cloud-computer-onboarding-commands-cdp.py --web-base http://106.55.62.122:3001 --api-base http://106.55.62.122:8011 --project-id fe9bd342-f5ef-4afe-9c73-e7caa2ed17dd --login-email 3245056131@qq.com --login-password password --output-dir artifacts
python scripts/validate-runner-watch-queue-http.py --api-base http://106.55.62.122:8011 --project-id fe9bd342-f5ef-4afe-9c73-e7caa2ed17dd --login-email 3245056131@qq.com --login-password password --output-dir artifacts
python scripts/validate-cloud-runner-command-routing.py --api-base http://106.55.62.122:8011 --project-id fe9bd342-f5ef-4afe-9c73-e7caa2ed17dd --login-email 3245056131@qq.com --login-password password
python scripts/validate-cloud-runner-dispatch-fullchain.py --api-base http://106.55.62.122:8011 --project-id fe9bd342-f5ef-4afe-9c73-e7caa2ed17dd --login-email 3245056131@qq.com --login-password password
python scripts/validate-cloud-runner-workstation-isolation.py --api-base http://106.55.62.122:8011 --project-id fe9bd342-f5ef-4afe-9c73-e7caa2ed17dd --login-email 3245056131@qq.com --login-password password
python scripts/validate-computer-thread-visibility-http.py --api-base http://106.55.62.122:8011 --web-base http://106.55.62.122:3001 --project-id fe9bd342-f5ef-4afe-9c73-e7caa2ed17dd --login-email 3245056131@qq.com --login-password password
python scripts/validate-desktop-need-task-roundtrip.py --api-base http://106.55.62.122:8011 --project-id fe9bd342-f5ef-4afe-9c73-e7caa2ed17dd --login-email 3245056131@qq.com --login-password password --workstation-id platform-npc-1 --runner-id runner-windows-desktop-main
python scripts/validate-structured-need-task-routing.py --api-base http://106.55.62.122:8011 --project-id fe9bd342-f5ef-4afe-9c73-e7caa2ed17dd --login-email 3245056131@qq.com --login-password password --requester-seat platform-npc-1 --target-seat platform-npc-2
npm run build:web
```

Expected result:

- API/Web alignment is `ok: true`.
- API/Web alignment prints the same `deployment.build_sha` through direct API and Web proxy.
- Windows and Linux onboarding commands are present.
- Cloud-rendered onboarding commands use public Web downloads on `3001` and public API calls on `8011`.
- Queue audit has no `issues`. Warnings are acceptable when an old command is explicitly waiting for an offline target computer.
- Runner registration leaves the computer node explicitly bound to the runner. If an old cloud build fails to bind during registration, the P0 scripts must detect that instead of pretending dispatch is ready.
- A command targeted at one computer is visible only to that computer's bound runner.
- A workstation/NPC inbox command can only be read, acked, and completed by the runner bound to that workstation's computer.
- Thread scan results appear in the computer panel as human-readable thread names; users do not type raw thread IDs.

## User-Visible Runner Semantics

Use these terms in UI and reports:

- `登记状态`: whether the computer node exists in the project.
- `Runner 心跳`: whether the runner has heartbeated recently.
- `常驻接单`: whether the runner watch window is open and polling.
- `扫描到线程`: thread names are known, but that does not mean the computer is currently accepting work.

Do not claim a computer can accept NPC work unless `runner_effective_status` is online or `runner_watch_state` is watching.

## Verified Evidence

Known reports:

- `artifacts/cloud-computer-onboarding-commands-report-20260517-174630.json`
- `artifacts/runner-watch-queue-http-report-20260517-174653.json`
- `artifacts/cloud-runner-command-routing/cloud-runner-command-routing-report-20260517-174653.json`
- `artifacts/cloud-runner-dispatch/cloud-runner-dispatch-fullchain-report-20260517-174653.json`
- `artifacts/cloud-runner-isolation/cloud-runner-workstation-isolation-report-20260517-174707.json`
- `artifacts/computer-thread-visibility-http-report-20260517-174707.json`

Latest deployed fingerprint:

- `deployment.build_sha`: `c21747744f65`
- `deployment.build_ref`: `ai/game-loop-core`
- `deployment.build_time`: `2026-05-17T09:45:49Z`

Validated paths:

- Cloud Web and API agree on the same deployed build fingerprint through direct API and Web proxy.
- Cloud-rendered pairing cards provide safe Windows and Linux/macOS watch commands, with public Web downloads on `3001` and public API calls on `8011`.
- Linux and Windows onboarding scripts are available through the download route and local compatibility checks pass.
- A synthetic runner can register, heartbeat, receive a cloud runner command, ack, complete, and expose visible receipts.
- Two synthetic runners bound to two different computers cannot see each other's targeted commands.
- A workstation command can be consumed only by the runner bound to that workstation's computer; wrong-runner read/ack is rejected.
- Thread scan sync makes scanned thread names visible in the cloud computer panel.
- A user-origin message typed in Codex Desktop can be synced back into platform messages as a Desktop question for the bound NPC.
- Need and Task queues are both executable enough to prove the loop: Need create -> Need dispatch message -> Need final reply, and Task create -> Task dispatch -> bound runner claim -> runner result.
- Structured NPC Need routing is explicit enough to prove the core contract: requester NPC creates a structured Need, route preview names a target NPC, route-to-task creates a Task, requester `my_needs` contains the Need, target `my_tasks` contains the Task, and the Task has a `created_from_need` event carrying the source Need id.

## Safety Boundary

Thread/NPC auto-execution remains opt-in. A runner can be online while a thread slot still reports manual mode. That is correct for safety:

- runner online means the computer can receive platform work;
- thread automation enabled means the bound thread may auto-process NPC commands;
- hardware, ROS write, firmware, motor, CAN write, and deployment actions still require explicit human approval.
