# Fixed Rehab Actions S-Curve Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one isolated smooth passive-training path where the App selects fixed rehab actions and the M33 executes them through a unified jerk-limited trajectory layer.

**Architecture:** Create a small reusable S-curve sampler and fixed-action runner in `applications/control`, then bridge it into the existing `rehab_service` and strict `rehab_ble_v1` path. The App gets a dedicated `smooth-training.html` page and mirrored Android WebView asset; future MuJoCo commands must enter through the same fixed motion command layer instead of direct motor setpoints.

**Tech Stack:** C on RT-Thread/M33, host C tests compiled by existing test runner patterns, Python static tests under `tools/`, static HTML/CSS/JS App assets under `F:\wt\platform-ai-latest`.

---

## File Map

- Create `applications/control/rehab_scurve.h`: reusable jerk-limited trajectory API.
- Create `applications/control/rehab_scurve.c`: bounded S-curve duration and sampling implementation.
- Create `tests/host/rehab_scurve_test.c`: host tests for continuity, bounds, late ticks, and synchronization.
- Create `applications/control/rehab_fixed_action.h`: fixed profile IDs, safe endpoints, runner API.
- Create `applications/control/rehab_fixed_action.c`: action profile table and state machine.
- Create `tests/host/rehab_fixed_action_test.c`: runner and profile validation tests.
- Modify `applications/control/rehab_service.h`: add `REHAB_DEMO_MODE_FIXED_ACTION` and fixed-action start/status API.
- Modify `applications/control/rehab_service.c`: own fixed-action runner in the worker and call prepare-once/setpoint-only control APIs.
- Modify `applications/control/control_layer.h`: add CSP session prepare and setpoint-only function declarations.
- Modify `applications/control/control_layer.c`: split one-time prepare from high-rate target update.
- Modify `applications/m33/app_ble_protocol.h`: add fixed profile enum values and masks for elbow, shoulder planar, coordinated, and disabled placeholder.
- Modify `applications/m33/app_ble_protocol.c`: parse fixed profile IDs and reject arbitrary parameters.
- Modify `tests/host/app_ble_protocol_test.c`: update fixed profile parser coverage.
- Modify `applications/control/rehab_mode_manager.h`: carry App fixed training profile through the manager.
- Modify `applications/control/rehab_mode_manager.c`: map fixed App training requests to `rehab_service_fixed_action_start_if_unchanged`.
- Modify `applications/m33/app_ble_worker.c`: pass fixed training enum into manager command.
- Create `tools/test_m33_fixed_action_static.py`: static boundary checks for no direct motor bypass and prepare-once usage.
- Create `F:\wt\platform-ai-latest\apps\web\public\rehab-arm-mobile\smooth-training.html`: dedicated App page.
- Modify `F:\wt\platform-ai-latest\apps\web\public\rehab-arm-mobile\home.html`: add one quiet entry to smooth training if navigation requires it.
- Modify `F:\wt\platform-ai-latest\apps\web\public\rehab-arm-mobile\sw.js`: include the new page in cache if this file currently enumerates assets.
- Mirror changed App files to `F:\wt\platform-ai-latest\apps\mobile\rehab-arm-android\www\`.
- Create `tools/test_rehab_mobile_smooth_training_static.py`: App forbidden-word and fixed-command checks.

## Task 0: Confirm App Baseline Before Edits

**Files:**
- Inspect: `F:\wt\platform-ai-latest`

- [ ] **Step 1: Check current App branch and remote state**

Run:

```powershell
rtk git -C F:\wt\platform-ai-latest status --short --branch
rtk git -C F:\wt\platform-ai-latest rev-parse HEAD
rtk git -C F:\wt\platform-ai-latest rev-parse origin/app/rehab-arm-mobile-stitch
```

Expected: local branch and remote SHA are visible; if local is behind and clean, fast-forward before editing.

- [ ] **Step 2: Fast-forward clean App checkout when possible**

Run only if `status --short` shows no local App edits:

```powershell
rtk git -C F:\wt\platform-ai-latest fetch origin app/rehab-arm-mobile-stitch
rtk git -C F:\wt\platform-ai-latest merge --ff-only origin/app/rehab-arm-mobile-stitch
```

Expected: fast-forward succeeds or reports already up to date.

- [ ] **Step 3: Stop if App has conflicting local edits**

If `status --short` shows local edits in the App checkout, do not overwrite them. Record the changed paths and ask the user before touching overlapping files.

## Task 1: Add Reusable S-Curve Sampler

**Files:**
- Create: `applications/control/rehab_scurve.h`
- Create: `applications/control/rehab_scurve.c`
- Test: `tests/host/rehab_scurve_test.c`

- [ ] **Step 1: Write the failing host test**

Create `tests/host/rehab_scurve_test.c` with tests shaped like:

```c
#include <assert.h>
#include <math.h>
#include "applications/control/rehab_scurve.h"

static void test_profile_starts_and_ends_at_rest(void)
{
    rehab_scurve_profile_t profile;
    rehab_scurve_sample_t sample;
    assert(rehab_scurve_plan(&profile, 6.226f, 8.038f, 0.12f, 0.20f, 0.50f) == RT_EOK);
    assert(rehab_scurve_sample(&profile, 0U, &sample) == RT_EOK);
    assert(fabsf(sample.position_rad - 6.226f) < 0.0001f);
    assert(fabsf(sample.velocity_rad_s) < 0.0001f);
    assert(rehab_scurve_sample(&profile, profile.duration_ms, &sample) == RT_EOK);
    assert(fabsf(sample.position_rad - 8.038f) <= 0.001f);
    assert(fabsf(sample.velocity_rad_s) < 0.0001f);
}

static void test_profile_respects_bounds_on_20ms_ticks(void)
{
    rehab_scurve_profile_t profile;
    rehab_scurve_sample_t prev;
    rt_uint32_t t;
    assert(rehab_scurve_plan(&profile, 3.689f, 4.944f, 0.12f, 0.20f, 0.50f) == RT_EOK);
    assert(rehab_scurve_sample(&profile, 0U, &prev) == RT_EOK);
    for (t = 20U; t <= profile.duration_ms + 20U; t += 20U)
    {
        rehab_scurve_sample_t sample;
        assert(rehab_scurve_sample(&profile, t, &sample) == RT_EOK);
        assert(sample.position_rad >= 3.689f - 0.001f);
        assert(sample.position_rad <= 4.944f + 0.001f);
        assert(fabsf(sample.velocity_rad_s) <= 0.121f);
        assert(fabsf(sample.position_rad - prev.position_rad) <= 0.01f);
        prev = sample;
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
rtk python tools/run_m33_gate01_host_tests.py
```

Expected: FAIL because `rehab_scurve.h` does not exist or test is not wired yet. If the runner does not discover the new test, add the test to the same host-test build list used for `rehab_curl_planner` and rerun until it fails for the missing implementation.

- [ ] **Step 3: Implement minimal S-curve API**

Add these public types and functions to `applications/control/rehab_scurve.h`:

```c
typedef struct
{
    float start_rad;
    float end_rad;
    float distance_rad;
    float direction;
    float max_velocity_rad_s;
    float max_accel_rad_s2;
    float max_jerk_rad_s3;
    rt_uint32_t duration_ms;
} rehab_scurve_profile_t;

typedef struct
{
    float position_rad;
    float velocity_rad_s;
    float accel_rad_s2;
} rehab_scurve_sample_t;

rt_err_t rehab_scurve_plan(rehab_scurve_profile_t *profile,
                           float start_rad,
                           float end_rad,
                           float max_velocity_rad_s,
                           float max_accel_rad_s2,
                           float max_jerk_rad_s3);
rt_err_t rehab_scurve_sample(const rehab_scurve_profile_t *profile,
                             rt_uint32_t elapsed_ms,
                             rehab_scurve_sample_t *out);
```

Implement `applications/control/rehab_scurve.c` with a minimum-jerk normalized trajectory:

```c
s = 10u^3 - 15u^4 + 6u^5
v = distance * (30u^2 - 60u^3 + 30u^4) / duration
a = distance * (60u - 180u^2 + 120u^3) / duration^2
```

Choose `duration_ms` by increasing from the distance/velocity estimate until sampled velocity and acceleration stay under limits. Keep jerk in the API and test budget even though the polynomial sampler bounds it indirectly by duration.

- [ ] **Step 4: Run S-curve tests to verify pass**

Run:

```powershell
rtk python tools/run_m33_gate01_host_tests.py
```

Expected: `rehab_scurve_test` passes and existing host tests remain green.

- [ ] **Step 5: Commit S-curve kernel**

Run:

```powershell
rtk git add applications/control/rehab_scurve.h applications/control/rehab_scurve.c tests/host/rehab_scurve_test.c tools/run_m33_gate01_host_tests.py
rtk git commit -m "feat(m33): add smooth scurve trajectory sampler"
```

## Task 2: Add Fixed Rehab Action Runner

**Files:**
- Create: `applications/control/rehab_fixed_action.h`
- Create: `applications/control/rehab_fixed_action.c`
- Test: `tests/host/rehab_fixed_action_test.c`

- [ ] **Step 1: Write failing fixed-action tests**

Create tests that assert:

```c
assert(rehab_fixed_action_profile(REHAB_FIXED_ACTION_ELBOW_FLEX_EXTEND)->joint_mask == 0x10U);
assert(rehab_fixed_action_profile(REHAB_FIXED_ACTION_SHOULDER_PLANAR)->joint_mask == 0x20U);
assert(rehab_fixed_action_profile(REHAB_FIXED_ACTION_COORDINATED)->joint_mask == 0x30U);
assert(rehab_fixed_action_start(&runner, REHAB_FIXED_ACTION_SHOULDER_FORE_AFT, feedback, now) == -RT_EINVAL);
```

Also assert a coordinated action returns setpoints for both moving joints at the same elapsed time and reaches COMPLETE after 3 round trips.

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
rtk python tools/run_m33_gate01_host_tests.py
```

Expected: FAIL because `rehab_fixed_action.h` does not exist.

- [ ] **Step 3: Implement fixed profile table and runner API**

Public enum in `rehab_fixed_action.h`:

```c
typedef enum
{
    REHAB_FIXED_ACTION_NONE = 0,
    REHAB_FIXED_ACTION_ELBOW_FLEX_EXTEND,
    REHAB_FIXED_ACTION_SHOULDER_PLANAR,
    REHAB_FIXED_ACTION_COORDINATED,
    REHAB_FIXED_ACTION_SHOULDER_FORE_AFT,
} rehab_fixed_action_id_t;
```

The profile table in `rehab_fixed_action.c` uses:

```c
joint 5: hard 6.000f..8.264f, safe 6.226f..8.038f
joint 6: hard 3.532f..5.101f, safe 3.689f..4.944f
limits: v=0.12f, a=0.20f, j=0.50f, dwell=500U, repetitions=3U
```

Runner states:

```c
IDLE, PRECHECK, CSP_PREPARE, ALIGN_FROM_CURRENT, MOVE_A, DWELL_A,
MOVE_B, DWELL_B, DECEL_STOP, COMPLETE, PAUSED, FAULT
```

- [ ] **Step 4: Run fixed-action tests to verify pass**

Run:

```powershell
rtk python tools/run_m33_gate01_host_tests.py
```

Expected: fixed-action tests pass and existing tests remain green.

- [ ] **Step 5: Commit fixed-action runner**

Run:

```powershell
rtk git add applications/control/rehab_fixed_action.h applications/control/rehab_fixed_action.c tests/host/rehab_fixed_action_test.c tools/run_m33_gate01_host_tests.py
rtk git commit -m "feat(m33): add fixed rehab action runner"
```

## Task 3: Integrate Runner Into M33 Service And Control Layer

**Files:**
- Modify: `applications/control/rehab_service.h`
- Modify: `applications/control/rehab_service.c`
- Modify: `applications/control/control_layer.h`
- Modify: `applications/control/control_layer.c`
- Create: `tools/test_m33_fixed_action_static.py`

- [ ] **Step 1: Write static tests for prepare-once and no bypass**

Create `tools/test_m33_fixed_action_static.py` with assertions:

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
service = (ROOT / "applications/control/rehab_service.c").read_text(encoding="utf-8")
control_h = (ROOT / "applications/control/control_layer.h").read_text(encoding="utf-8")

def test_fixed_action_mode_is_present():
    header = (ROOT / "applications/control/rehab_service.h").read_text(encoding="utf-8")
    assert "REHAB_DEMO_MODE_FIXED_ACTION" in header
    assert "rehab_service_fixed_action_start_if_unchanged" in header

def test_service_uses_prepare_once_and_setpoint_only():
    assert "control_motor_csp_prepare" in control_h
    assert "control_motor_csp_setpoint" in control_h
    assert "rehab_fixed_action_step" in service
    assert "control_motor_position_control_with_current_limit(" not in service[service.find("REHAB_DEMO_MODE_FIXED_ACTION"):]
```

- [ ] **Step 2: Run static test to verify it fails**

Run:

```powershell
rtk python -m unittest tools.test_m33_fixed_action_static -v
```

Expected: FAIL because fixed-action service API and CSP split do not exist.

- [ ] **Step 3: Add service API and status fields**

In `rehab_service.h`, add:

```c
REHAB_DEMO_MODE_FIXED_ACTION,
rt_err_t rehab_service_fixed_action_start_if_unchanged(
    rehab_fixed_action_id_t action,
    rehab_cmd_source_t source,
    rehab_cmd_source_t expected_source,
    rt_uint32_t expected_generation);
```

Add `fixed_action_id`, `fixed_action_state`, `fixed_action_repetitions`, and `fixed_action_fault` to `rehab_service_status_t`.

- [ ] **Step 4: Split control-layer CSP prepare and setpoint**

Add declarations:

```c
rt_err_t control_motor_csp_prepare(rt_uint8_t m33_joint_id, float current_limit_a);
rt_err_t control_motor_csp_setpoint(rt_uint8_t m33_joint_id, float target_pos_rad);
rt_err_t control_motor_csp_group_stop(rt_uint8_t joint_mask);
```

In `control_layer.c`, move the one-time mode setup, enable, and parameter writes out of `control_motor_position_control_with_current_limit()` into `control_motor_csp_prepare()`. Keep `control_motor_position_control_with_current_limit()` as a compatibility wrapper for old callers.

- [ ] **Step 5: Wire fixed-action runner in `rehab_service.c`**

Add `rehab_fixed_action_runner_t fixed_action_runner;` to `rehab_service_runtime_t`. During `REHAB_DEMO_MODE_FIXED_ACTION`, use feedback snapshots, call `rehab_fixed_action_step()`, call `control_motor_csp_prepare()` only when entering `CSP_PREPARE`, and call `control_motor_csp_setpoint()` during MOVE states.

- [ ] **Step 6: Run service/control tests**

Run:

```powershell
rtk python -m unittest tools.test_m33_fixed_action_static tools.test_rehab_mode_static tools.test_rehab_app_manager_static -v
rtk python tools/run_m33_gate01_host_tests.py
```

Expected: all listed tests pass.

- [ ] **Step 7: Commit service integration**

Run:

```powershell
rtk git add applications/control/rehab_service.h applications/control/rehab_service.c applications/control/control_layer.h applications/control/control_layer.c tools/test_m33_fixed_action_static.py
rtk git commit -m "feat(m33): route fixed actions through smooth control"
```

## Task 4: Extend BLE Fixed Profile Contract

**Files:**
- Modify: `applications/m33/app_ble_protocol.h`
- Modify: `applications/m33/app_ble_protocol.c`
- Modify: `tests/host/app_ble_protocol_test.c`
- Modify: `applications/control/rehab_mode_manager.h`
- Modify: `applications/control/rehab_mode_manager.c`
- Modify: `applications/m33/app_ble_worker.c`

- [ ] **Step 1: Write failing BLE parser tests**

In `tests/host/app_ble_protocol_test.c`, add accepted profile frames:

```c
"fixed_elbow_flex_extend_v1" with joint_mask 16
"fixed_shoulder_planar_v1" with joint_mask 32
"fixed_coordinated_elbow_shoulder_v1" with joint_mask 48
```

Add rejected frames:

```c
"fixed_shoulder_fore_aft_v1"
any training_request containing raw, velocity, current, target, points, or repeat_count fields
```

- [ ] **Step 2: Run parser test to verify it fails**

Run:

```powershell
rtk python tools/run_m33_gate01_host_tests.py
```

Expected: FAIL because the new profile strings are not parsed.

- [ ] **Step 3: Add BLE enum values and masks**

In `app_ble_protocol.h`, add:

```c
#define APP_BLE_PROTOCOL_FIXED_ELBOW_MASK 0x10u
#define APP_BLE_PROTOCOL_FIXED_SHOULDER_PLANAR_MASK 0x20u
#define APP_BLE_PROTOCOL_FIXED_COORDINATED_MASK 0x30u

APP_BLE_TRAINING_FIXED_ELBOW_FLEX_EXTEND,
APP_BLE_TRAINING_FIXED_SHOULDER_PLANAR,
APP_BLE_TRAINING_FIXED_COORDINATED,
APP_BLE_TRAINING_FIXED_SHOULDER_FORE_AFT
```

Map accepted profile strings to the first three enum values. Parse the disabled placeholder string but reject it at final validation so App gets a controlled rejection.

- [ ] **Step 4: Carry fixed training through manager**

Add `app_ble_training_t training;` or a local fixed-action enum to `rehab_app_mode_command_t`. In `app_ble_worker.c`, copy `request.training` into the manager command. In `rehab_mode_manager.c`, map fixed profile values to `rehab_service_fixed_action_start_if_unchanged()`.

- [ ] **Step 5: Run BLE and manager tests**

Run:

```powershell
rtk python tools/run_m33_gate01_host_tests.py
rtk python -m unittest tools.test_rehab_app_manager_static tools.test_rehab_command_source_static -v
```

Expected: all listed tests pass.

- [ ] **Step 6: Commit BLE contract**

Run:

```powershell
rtk git add applications/m33/app_ble_protocol.h applications/m33/app_ble_protocol.c tests/host/app_ble_protocol_test.c applications/control/rehab_mode_manager.h applications/control/rehab_mode_manager.c applications/m33/app_ble_worker.c
rtk git commit -m "feat(m33): accept fixed rehab action profiles over ble"
```

## Task 5: Add Dedicated Smooth Training App Page

**Files:**
- Create: `F:\wt\platform-ai-latest\apps\web\public\rehab-arm-mobile\smooth-training.html`
- Modify: `F:\wt\platform-ai-latest\apps\web\public\rehab-arm-mobile\home.html`
- Modify: `F:\wt\platform-ai-latest\apps\web\public\rehab-arm-mobile\sw.js`
- Mirror to: `F:\wt\platform-ai-latest\apps\mobile\rehab-arm-android\www\`
- Create: `tools/test_rehab_mobile_smooth_training_static.py`

- [ ] **Step 1: Write failing App static test**

Create `tools/test_rehab_mobile_smooth_training_static.py`:

```python
from pathlib import Path

WEB = Path(r"F:\wt\platform-ai-latest\apps\web\public\rehab-arm-mobile")
MOBILE = Path(r"F:\wt\platform-ai-latest\apps\mobile\rehab-arm-android\www")
FORBIDDEN = ["电机", "4号", "5号", "6号", "raw", "rad", "电流", "速度", "S曲线", "LADRC", "ADRC", "CSP", "协议", "调试", "工程模式", "AI方案", "助力", "阻力", "自由轨迹", "云端", "ROS", "NanoPi", "MuJoCo"]

def test_smooth_training_page_copy_and_forbidden_words():
    text = (WEB / "smooth-training.html").read_text(encoding="utf-8")
    for required in ["平稳动作训练", "肘部屈伸", "肩部平转", "协同训练", "肩部前后", "3次往返", "开始训练", "平稳运行中"]:
        assert required in text
    for forbidden in FORBIDDEN:
        assert forbidden not in text

def test_page_sends_only_fixed_profiles():
    text = (WEB / "smooth-training.html").read_text(encoding="utf-8")
    for profile in ["fixed_elbow_flex_extend_v1", "fixed_shoulder_planar_v1", "fixed_coordinated_elbow_shoulder_v1"]:
        assert profile in text
    for forbidden_key in ["target", "points", "velocity", "current", "raw", "repeat_count"]:
        assert forbidden_key not in text

def test_webview_mirror_matches_web_page():
    assert (WEB / "smooth-training.html").read_text(encoding="utf-8") == (MOBILE / "smooth-training.html").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run App static test to verify it fails**

Run:

```powershell
rtk python -m unittest tools.test_rehab_mobile_smooth_training_static -v
```

Expected: FAIL because `smooth-training.html` does not exist.

- [ ] **Step 3: Build the static page from the Stitch contract**

Create `smooth-training.html` with:

- Title `平稳动作训练`
- Connection card `设备已连接 / 可以开始训练`
- Four action cards, with `肘部屈伸` selected and `肩部前后` disabled
- Fixed `3次往返`
- Buttons `开始训练`, `暂停`, `停止训练`
- Safety copy exactly matching the spec
- JavaScript that sends `training_request` frames with only `schema`, `type`, `request_id`, `profile`, `joint_mask`, and `ttl_ms`
- Heartbeat timer while running
- Stop on page leave and disconnect hooks through existing `mobile-bridge.js`

- [ ] **Step 4: Add minimal navigation without mixing modes**

If `home.html` has a bottom nav or training entry list, add one entry labeled `平稳动作训练` linking to `smooth-training.html`. Do not add links from `ai-plan.html`, assist, resist, or debug pages.

- [ ] **Step 5: Mirror App assets**

Copy changed web files into `F:\wt\platform-ai-latest\apps\mobile\rehab-arm-android\www\` using the same filenames.

- [ ] **Step 6: Run App static verification**

Run:

```powershell
rtk python -m unittest tools.test_rehab_mobile_smooth_training_static -v
rtk python tools/verify_rehab_mobile_webview_mirror.py
```

Expected: new static test passes and WebView mirror verification passes.

- [ ] **Step 7: Commit App and static tests**

Run:

```powershell
rtk git add tools/test_rehab_mobile_smooth_training_static.py
rtk git commit -m "test(app): cover smooth training page contract"
rtk git -C F:\wt\platform-ai-latest add apps/web/public/rehab-arm-mobile/smooth-training.html apps/web/public/rehab-arm-mobile/home.html apps/web/public/rehab-arm-mobile/sw.js apps/mobile/rehab-arm-android/www/smooth-training.html apps/mobile/rehab-arm-android/www/home.html apps/mobile/rehab-arm-android/www/sw.js
rtk git -C F:\wt\platform-ai-latest commit -m "feat(app): add smooth fixed-action training page"
```

## Task 6: Final Verification And Bench Gate

**Files:**
- Inspect: current M33 repo
- Inspect: `F:\wt\platform-ai-latest`

- [ ] **Step 1: Run full host/static verification**

Run:

```powershell
rtk python tools/run_m33_gate01_host_tests.py
rtk python -m unittest tools.test_m33_fixed_action_static tools.test_rehab_app_manager_static tools.test_rehab_command_source_static tools.test_rehab_mobile_smooth_training_static -v
```

Expected: all tests pass.

- [ ] **Step 2: Build M33 firmware**

Run:

```powershell
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4
```

Expected: build exits 0.

- [ ] **Step 3: Record software acceptance status**

Create or update a small evidence note under `docs/qa/` that lists the exact commands above and their pass/fail result. If any hardware test has not been run, write `hardware bench not run in this session`.

- [ ] **Step 4: Hardware acceptance sequence**

On bench, run only one fixed single-action profile first:

```text
1. Connect BLE.
2. Open 平稳动作训练.
3. Select 肘部屈伸.
4. Start at 1.0 A commissioning limit.
5. Verify no start/stop shock and no mid-motion oscillation.
6. Stop and confirm controlled stop.
7. Only after this passes, test 肩部平转.
8. Only after both pass, test 协同训练.
```

- [ ] **Step 5: Final commit for evidence**

Run:

```powershell
rtk git add docs/qa
rtk git commit -m "test(m33): record smooth fixed-action acceptance"
```

## Self-Review

- Spec coverage: fixed App page, disabled shoulder fore/aft, no user-visible motor numbers, unified trajectory layer, future MuJoCo entry constraint, S-curve limits, state machine, BLE fixed profiles, App mirror, tests, and build verification are covered.
- Placeholder scan: no task contains placeholder markers or unspecified implementation targets.
- Type consistency: `rehab_fixed_action_id_t`, `rehab_scurve_profile_t`, `rehab_app_mode_command_t`, and fixed BLE profile names are used consistently across tasks.
- Scope check: assist, resist, ROS, NanoPi, cloud plans, and memory playback remain outside the edited path.
