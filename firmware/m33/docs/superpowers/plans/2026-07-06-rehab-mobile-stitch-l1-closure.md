# Rehab Mobile Stitch L1 Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the rehab mobile app from API-ready staging to L1 User-Ready Staging by having Stitch replace the current debug/static frontend with the live patient-view and Ask Therapist flows, then have Codex deploy and verify the result.

**Architecture:** Stitch owns frontend edits on `app/rehab-arm-mobile-stitch`; Codex owns backend, QA gates, deployment, APK verification, browser screenshots, and git commits. The web frontend under `apps/web/public/rehab-arm-mobile/` is the primary source for cloud deployment, and accepted assets must be mirrored into `apps/mobile/rehab-arm-android/www/` before APK packaging so installed APK behavior matches web behavior.

**Tech Stack:** Static HTML/CSS/JS mobile frontend, FastAPI-compatible rehab cloud API at `http://106.55.62.122:8011`, Codex QA scripts in `tools/`, in-app browser QA at `390 x 844`, guarded SSH deploy tooling.

---

### Task 1: Hand Stitch The Current Source Scope

**Files:**
- Read: `docs/stitch/rehab-mobile-l1-stitch-execution-v4-20260706.md`
- Read: `docs/stitch/rehab-mobile-l1-repair-packet-20260706.json`
- Read: `docs/stitch/rehab-mobile-l1-api-fixture-20260706.json`
- Source branch: `app/rehab-arm-mobile-stitch`
- Web edit path: `apps/web/public/rehab-arm-mobile/`
- APK WebView mirror path: `apps/mobile/rehab-arm-android/www/`

- [ ] **Step 1: Confirm the source branch and commit**

Run:

```powershell
git ls-remote --heads https://github.com/wenjunyong666/ai-.git app/rehab-arm-mobile-stitch
```

Expected: output contains `refs/heads/app/rehab-arm-mobile-stitch`.

- [ ] **Step 2: Give Stitch the prompt and packet**

Use the full contents of:

```text
docs/stitch/rehab-mobile-l1-stitch-execution-v4-20260706.md
docs/stitch/rehab-mobile-l1-repair-packet-20260706.json
```

Expected Stitch output: edited frontend files under `apps/web/public/rehab-arm-mobile/`, with equivalent assets ready to mirror into `apps/mobile/rehab-arm-android/www/`.

- [ ] **Step 3: Reject non-frontend changes from Stitch**

Run:

```powershell
git diff --name-only
```

Expected: changed files are only under `apps/web/public/rehab-arm-mobile/`, `apps/mobile/rehab-arm-android/www/`, or documented frontend release artifacts. Backend files are unchanged.

### Task 2: Local Frontend L1 Preflight

**Files:**
- Validate: `apps/web/public/rehab-arm-mobile/home.html`
- Validate: `apps/web/public/rehab-arm-mobile/profile.html`
- Validate: `apps/web/public/rehab-arm-mobile/device.html`
- Validate: `apps/web/public/rehab-arm-mobile/ai-plan.html`
- Output: `artifacts/rehab-mobile-frontend-release/frontend-l1-preflight.json`

- [ ] **Step 1: Run the static/source L1 gate**

Run:

```powershell
.\cloud\rehab-platform\.venv\Scripts\python.exe tools\qa_rehab_mobile_l1_frontend.py --source-dir apps/web/public/rehab-arm-mobile --output artifacts/rehab-mobile-frontend-release/frontend-l1-preflight.json
```

Expected: exit code `0`, `summary.overall = PASS`, `summary.failed = 0`.

- [ ] **Step 2: Inspect the preflight JSON**

Run:

```powershell
.\cloud\rehab-platform\.venv\Scripts\python.exe -c "import json; p='artifacts/rehab-mobile-frontend-release/frontend-l1-preflight.json'; d=json.load(open(p,encoding='utf-8')); print(d['summary'])"
```

Expected: no missing `patient_view_*`, phone, device, Agent message, unsafe refusal, or model status requirements.

### Task 3: Mirror Web Assets For APK

**Files:**
- Source: `apps/web/public/rehab-arm-mobile/`
- Destination: `apps/mobile/rehab-arm-android/www/`

- [ ] **Step 1: Copy accepted web assets into the Android WebView bundle**

Run:

```powershell
robocopy apps\web\public\rehab-arm-mobile apps\mobile\rehab-arm-android\www /MIR
if ($LASTEXITCODE -le 7) { $global:LASTEXITCODE = 0 }
```

Expected: Android `www` files match the accepted web frontend, and command exits `0`.

- [ ] **Step 2: Verify Android WebView mirror parity**

Run:

```powershell
.\cloud\rehab-platform\.venv\Scripts\python.exe tools\verify_rehab_mobile_webview_mirror.py --web-dir apps/web/public/rehab-arm-mobile --android-www-dir apps/mobile/rehab-arm-android/www --output artifacts/rehab-mobile-frontend-release/webview-mirror-verification.json
```

Expected: exit code `0`, `summary.overall = PASS`, no missing, changed, or extra files.

- [ ] **Step 3: Re-run local L1 gate against the mirrored APK assets**

Run:

```powershell
.\cloud\rehab-platform\.venv\Scripts\python.exe tools\qa_rehab_mobile_l1_frontend.py --source-dir apps/mobile/rehab-arm-android/www --output artifacts/rehab-mobile-frontend-release/apk-www-l1-preflight.json
```

Expected: exit code `0`, `summary.overall = PASS`, `summary.failed = 0`.

### Task 4: Package And Deploy Web Frontend

**Files:**
- Input: `apps/web/public/rehab-arm-mobile/`
- Output: `artifacts/rehab-mobile-frontend-release/rehab-mobile-frontend-release-manifest.json`
- Output: `artifacts/rehab-mobile-frontend-release/rehab-mobile-frontend-release.zip`

- [ ] **Step 1: Build the guarded release bundle**

Run:

```powershell
.\cloud\rehab-platform\.venv\Scripts\python.exe tools\prepare_rehab_mobile_frontend_release.py --source-dir apps/web/public/rehab-arm-mobile --output-dir artifacts/rehab-mobile-frontend-release
```

Expected: exit code `0`, manifest and zip are written.

- [ ] **Step 2: Verify the release manifest**

Run:

```powershell
.\cloud\rehab-platform\.venv\Scripts\python.exe tools\verify_rehab_mobile_frontend_release.py --manifest artifacts/rehab-mobile-frontend-release/rehab-mobile-frontend-release-manifest.json --output artifacts/rehab-mobile-frontend-release/frontend-release-verification.json
```

Expected: exit code `0`, `summary.overall = PASS`.

- [ ] **Step 3: Dry-run cloud deployment**

Run:

```powershell
.\cloud\rehab-platform\.venv\Scripts\python.exe tools\deploy_rehab_mobile_frontend_release.py --manifest artifacts/rehab-mobile-frontend-release/rehab-mobile-frontend-release-manifest.json
```

Expected: dry-run output lists `scp`, `ssh`, remote backup, and post-deploy verification commands.

- [ ] **Step 4: Execute cloud deployment after reviewing the dry-run**

Run:

```powershell
.\cloud\rehab-platform\.venv\Scripts\python.exe tools\deploy_rehab_mobile_frontend_release.py --manifest artifacts/rehab-mobile-frontend-release/rehab-mobile-frontend-release-manifest.json --execute --run-post-verify
```

Expected: exit code `0`, post-deploy verification commands complete.

### Task 5: Combined L1 And Browser QA

**Files:**
- Output: `docs/qa/rehab-mobile-20260706/screenshots/l1-home-390.png`
- Output: `docs/qa/rehab-mobile-20260706/screenshots/l1-ask-therapist-chat-390.png`
- Output: `docs/qa/rehab-mobile-20260706/screenshots/l1-unsafe-agent-refusal-390.png`
- Output: `docs/qa/rehab-mobile-20260706/screenshots/l1-device-binding-wizard-390.png`
- Output: `docs/qa/rehab-mobile-20260706/screenshots/l1-profile-phone-medical-390.png`

- [ ] **Step 1: Run combined L1 release**

Run with QA credentials already present in the shell environment:

```powershell
.\cloud\rehab-platform\.venv\Scripts\python.exe tools\qa_rehab_mobile_l1_release.py
```

Expected: exit code `0`, `summary.overall = PASS`, `summary.blocking_gates = []`.

- [ ] **Step 2: Run objective audit**

Run:

```powershell
.\cloud\rehab-platform\.venv\Scripts\python.exe tools\qa_rehab_mobile_l1_objective_audit.py
```

Expected: exit code `0`, `summary.overall = PASS`, `summary.blocking_requirements = []`.

- [ ] **Step 3: Capture final browser QA screenshots**

Use the Codex in-app browser at exactly `390 x 844` and save the five required screenshot files listed above.

Expected: each file decodes to `390 x 844` and shows the required scene.

- [ ] **Step 4: Export final L1 evidence**

Run:

```powershell
.\cloud\rehab-platform\.venv\Scripts\python.exe tools\export_rehab_mobile_l1_evidence.py --output artifacts\rehab-mobile-l1-evidence\rehab-mobile-l1-evidence.json --fail-on-l1-fail
```

Expected: exit code `0`, `summary.overall = PASS`, `health_ok = true`, `apk_ok = true`.

### Task 6: APK And Git Closeout

**Files:**
- Update: `docs/qa/rehab-mobile-20260706/QA_REPORT.md`
- Update: `docs/qa/rehab-mobile-20260706/APP_COMPLETION_SCORECARD.md`
- Commit all task-relevant frontend, QA, evidence, and packaging artifacts only.

- [ ] **Step 1: Verify APK delivery**

Run:

```powershell
curl.exe -I -sS http://106.55.62.122:3001/downloads/rehab-arm/lingdong-rehab-arm-debug.apk
```

Expected: `200 OK`, APK content type, size over 1 MB.

- [ ] **Step 2: Check git scope**

Run:

```powershell
git status --short
git diff --check
```

Expected: only task-relevant files are changed, and `git diff --check` prints no errors.

- [ ] **Step 3: Commit**

Run:

```powershell
git add apps/web/public/rehab-arm-mobile apps/mobile/rehab-arm-android/www docs/qa/rehab-mobile-20260706 docs/stitch artifacts/rehab-mobile-frontend-release
git commit -m "feat: close rehab mobile l1 frontend"
```

Expected: a focused commit exists and can be referenced in the QA report.

## Self-Review

- Spec coverage: the plan covers login/API, home next step, phone UI, device UI, Ask Therapist, unsafe refusal, no fake profile data, browser screenshots, cloud deploy, APK verification, and git commit.
- Placeholder scan: private QA credentials are intentionally supplied through environment variables at execution time and are not written into the plan.
- Type consistency: paths match the current Stitch prompt and repair packet fields, including the web edit path and Android WebView mirror path.
