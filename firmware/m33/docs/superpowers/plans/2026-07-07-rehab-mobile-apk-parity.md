# Rehab Mobile APK Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a signed staging APK whose bundled WebView assets match the accepted L1 mobile app files.

**Architecture:** Reuse the existing debug APK as a native template, replace only `assets/public/` with `apps/mobile/rehab-arm-android/www/`, run `zipalign`, sign with a generated Android debug key, then verify with `tools/verify_rehab_mobile_apk_webview_assets.py` and `apksigner verify`. The toolchain is local JDK `F:\Java\temurin-17\jdk-17.0.19+10` plus Android SDK build-tools `F:\Android\Sdk\build-tools\36.0.0`.

**Tech Stack:** Python zipfile tooling, Android SDK `zipalign` and `apksigner`, JDK `keytool`, pytest, existing rehab mobile L1 QA scripts.

---

### Task 1: Package Tool

**Files:**
- Create: `tools/package_rehab_mobile_apk_webview_assets.py`
- Test: `tools/test_package_rehab_mobile_apk_webview_assets.py`

- [ ] **Step 1: Write the failing unit test**

Run:

```powershell
F:\Anaconda\python.exe -m pytest tools/test_package_rehab_mobile_apk_webview_assets.py -q
```

Expected before implementation: import failure or missing `package_webview_assets` behavior.

- [ ] **Step 2: Implement the minimal package helper**

The helper copies every non-`assets/public/` entry from the template APK, skips signing entries under `META-INF/`, adds current Android `www` files under `assets/public/`, and writes an unsigned intermediate APK.

- [ ] **Step 3: Run unit tests**

Run:

```powershell
F:\Anaconda\python.exe -m pytest tools/test_package_rehab_mobile_apk_webview_assets.py tools/test_verify_rehab_mobile_apk_webview_assets.py -q
```

Expected after implementation: all tests pass.

### Task 2: Real APK Build

**Files:**
- Input: `artifacts/external/rehab-arm-mobile-stitch/apps/web/public/downloads/rehab-arm/lingdong-rehab-arm-debug.apk`
- Input: `artifacts/external/rehab-arm-mobile-stitch/apps/mobile/rehab-arm-android/www/`
- Output: `artifacts/external/rehab-arm-mobile-stitch/apps/web/public/downloads/rehab-arm/lingdong-rehab-arm-l1-staging.apk`
- Output: `docs/qa/rehab-mobile-20260706/apk-package-l1-staging-20260707.json`

- [ ] **Step 1: Generate the staging APK**

Run:

```powershell
F:\Anaconda\python.exe tools/package_rehab_mobile_apk_webview_assets.py --template-apk artifacts/external/rehab-arm-mobile-stitch/apps/web/public/downloads/rehab-arm/lingdong-rehab-arm-debug.apk --android-www-dir artifacts/external/rehab-arm-mobile-stitch/apps/mobile/rehab-arm-android/www --output-apk artifacts/external/rehab-arm-mobile-stitch/apps/web/public/downloads/rehab-arm/lingdong-rehab-arm-l1-staging.apk --java-home F:\Java\temurin-17\jdk-17.0.19+10 --build-tools-dir F:\Android\Sdk\build-tools\36.0.0 --report docs/qa/rehab-mobile-20260706/apk-package-l1-staging-20260707.json
```

Expected: exit code `0`, signed APK exists, report says `overall = PASS`.

- [ ] **Step 2: Verify APK WebView asset parity**

Run:

```powershell
F:\Anaconda\python.exe tools/verify_rehab_mobile_apk_webview_assets.py --apk artifacts/external/rehab-arm-mobile-stitch/apps/web/public/downloads/rehab-arm/lingdong-rehab-arm-l1-staging.apk --android-www-dir artifacts/external/rehab-arm-mobile-stitch/apps/mobile/rehab-arm-android/www --asset-prefix assets/public --output docs/qa/rehab-mobile-20260706/apk-webview-assets-l1-staging-20260707.json
```

Expected: exit code `0`, `summary.overall = PASS`.

- [ ] **Step 3: Verify Android signature**

Run:

```powershell
$env:JAVA_HOME='F:\Java\temurin-17\jdk-17.0.19+10'; $env:Path="$env:JAVA_HOME\bin;$env:Path"; F:\Android\Sdk\build-tools\36.0.0\apksigner.bat verify --verbose artifacts\external\rehab-arm-mobile-stitch\apps\web\public\downloads\rehab-arm\lingdong-rehab-arm-l1-staging.apk
```

Expected: `Verifies` and v2 verification is `true`.

### Task 3: Release Gates And Git

**Files:**
- Output: `docs/qa/rehab-mobile-20260706/l1-release-l1-staging-apk-20260707.json`
- Output: `docs/qa/rehab-mobile-20260706/objective-audit-l1-staging-apk-20260707.json`

- [ ] **Step 1: Run the combined release gate against the new APK**

Run:

```powershell
F:\Anaconda\python.exe tools/qa_rehab_mobile_l1_release.py --api-base http://106.55.62.122:8011 --frontend-source-dir artifacts/external/rehab-arm-mobile-stitch/apps/mobile/rehab-arm-android/www --apk artifacts/external/rehab-arm-mobile-stitch/apps/web/public/downloads/rehab-arm/lingdong-rehab-arm-l1-staging.apk --android-www-dir artifacts/external/rehab-arm-mobile-stitch/apps/mobile/rehab-arm-android/www --output docs/qa/rehab-mobile-20260706/l1-release-l1-staging-apk-20260707.json
```

Expected: exit code `0`, `summary.overall = PASS`.

- [ ] **Step 2: Run objective audit with browser evidence**

Run:

```powershell
F:\Anaconda\python.exe tools/qa_rehab_mobile_l1_objective_audit.py --release-json docs/qa/rehab-mobile-20260706/l1-release-l1-staging-apk-20260707.json --browser-metrics-json docs/qa/rehab-mobile-20260706/browser-metrics-cloud-runtime-indexed-20260707.json --output docs/qa/rehab-mobile-20260706/objective-audit-l1-staging-apk-20260707.json
```

Expected: APK and combined release requirements pass; any remaining failure is a real objective gap to fix next.

- [ ] **Step 3: Commit and push**

Run:

```powershell
git add tools/package_rehab_mobile_apk_webview_assets.py tools/test_package_rehab_mobile_apk_webview_assets.py docs/superpowers/plans/2026-07-07-rehab-mobile-apk-parity.md docs/qa/rehab-mobile-20260706
git commit -m "Package rehab mobile L1 staging APK"
git push
```
