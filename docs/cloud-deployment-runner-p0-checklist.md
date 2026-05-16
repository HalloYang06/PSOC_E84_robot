# Cloud Deployment Runner P0 Checklist

Last verified: 2026-05-16

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

## P0 Validation

Run from the development machine:

```powershell
python scripts/check_web_api_alignment.py --web-base http://106.55.62.122:3001 --api-base http://106.55.62.122:8011 --project-id 72a1cb1d-d8a8-422f-8d87-4ed071f71dbe
python scripts/validate-cross-platform-runner-onboarding.py
python scripts/validate-cloud-computer-onboarding-commands-cdp.py --web-base http://106.55.62.122:3001 --api-base http://106.55.62.122:8011 --project-id 72a1cb1d-d8a8-422f-8d87-4ed071f71dbe --login-email 3245056131@qq.com --login-password password --output-dir artifacts
python scripts/validate-runner-watch-queue-http.py --api-base http://106.55.62.122:8011 --project-id 72a1cb1d-d8a8-422f-8d87-4ed071f71dbe --login-email 3245056131@qq.com --login-password password --output-dir artifacts --strict
```

Expected result:

- API/Web alignment is `ok: true`.
- Windows and Linux onboarding commands are present.
- Cloud-rendered onboarding commands use public Web downloads on `3001` and public API calls on `8011`.
- Queue audit has no `issues`. Warnings are acceptable when an old command is explicitly waiting for an offline target computer.

## User-Visible Runner Semantics

Use these terms in UI and reports:

- `登记状态`: whether the computer node exists in the project.
- `Runner 心跳`: whether the runner has heartbeated recently.
- `常驻接单`: whether the runner watch window is open and polling.
- `扫描到线程`: thread names are known, but that does not mean the computer is currently accepting work.

Do not claim a computer can accept NPC work unless `runner_effective_status` is online or `runner_watch_state` is watching.

## Verified Evidence

Known reports:

- `artifacts/p0-cloud-cross-platform-runner-report-20260516160900.json`
- `artifacts/cloud-computer-onboarding-commands-report-20260516-162035.json`
- `artifacts/runner-watch-queue-http-report-20260516-161612.json`

Validated paths:

- Linux cloud runner registered from cloud-downloaded `connect-ai-collab-runner.sh`.
- Windows runner registered from cloud-downloaded `connect-ai-collab-runner.ps1`.
- Cloud runner commands reached both Windows and Linux runners and completed.
- A Windows thread slot received a cloud workstation command through `platform-workstation-adapter.py` and wrote ack/final receipts without executing provider CLI.

## Safety Boundary

Thread/NPC auto-execution remains opt-in. A runner can be online while a thread slot still reports manual mode. That is correct for safety:

- runner online means the computer can receive platform work;
- thread automation enabled means the bound thread may auto-process NPC commands;
- hardware, ROS write, firmware, motor, CAN write, and deployment actions still require explicit human approval.
