# M33 Gate 0-1 Scheduling, Safety, and Assist Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Use superpowers:test-driven-development for each behavior change and superpowers:verification-before-completion before every completion claim.

**Goal:** 在不扩大 BLE、IPC V2、云端或多关节控制范围的前提下，先把当前 M33 固件变成可追溯、可调度、默认失效安全的版本，再恢复单关节助力链路的连续心跳、统一 prearm、一次性电机使能和确定周期 setpoint。

**Architecture:** 保持 `ctrl_can` 为唯一 CAN RX 消费者，保留一个 `rehab_svc` 线程作为康复命令与运动状态的唯一执行者，不再新增 manager/timer 线程。CAN 与 Shell 只向固定队列提交请求；纯逻辑 `control_prearm` 负责准入判定；`rehab_motor_session` 负责 `DISARMED -> ARMING -> READY -> FAULT/PASSIVE` 生命周期；高频循环只写电流 setpoint。所有默认构建 fail closed，STOP 在任何状态下均可执行。

**Tech Stack:** C11、RT-Thread 5.0.2、Infineon PSoC Edge M33、SCons 4.10、MinGW GCC host tests、Python `unittest` 静态/manifest 测试、现有 `can_metrics`、RT-Thread `list thread` 与 `list memheap`。

---

## 0. Scope And Safety Contract

本计划中的“Gate 1”是紧急稳定批次，不等于总审计文档中完整的工业 CAN/IPC 改造。完成后可以宣称：M33 关键线程可调度、CAN RX 单消费者、康复命令单执行者、单关节助力具备基本安全闭环。仍然不能宣称：CAN TX 已单 owner、CAN 已达到工业级、双核 IPC exactly-once、推理结果稳定上云、BLE 已可发布或已具备临床安全性。

明确不在本批次修改：

- `drv_can.c/.h` 的 mailbox、MRAM、恢复时序和过滤器。
- `m33_m55_message_t`、共享 SRAM 布局、IPC queue depth 和超时。
- NanoPi outbox、云端幂等、App/BLE 配对。
- motor3 自动加入 assist；现有 assist 组 `0x38` 仍表示 motor4/5/6。
- 多关节 assist、人体佩戴、临床 profile。
- PID/ADRC 参数调优；本批只修正调度、`dt`、方向、限幅和执行生命周期。

必须始终满足的安全不变量：

1. 默认源码构建为 `bench=0`、`clinical=0`、`logging_only=1`。
2. 不得把 `*_CONFIRMED` 或 `*_SAFE_NOW` 直接改成 `1` 来绕过硬件验收。
3. 第一次调度修复镜像只能在电机断电、动力线断开或驱动器禁止输出时烧录。
4. STOP 不依赖 heartbeat、owner、prearm 或命令队列空闲，且不能因队列满而丢失。
5. 任何 mutex 都不能跨 CAN 发送、`rt_thread_mdelay()`、电机 enable/stop 或日志输出持有。
6. 高频任务不得逐周期 `rt_kprintf`、动态分配或永久等待锁。
7. 首轮有动力测试只能单关节、空载/悬空、现场物理断电手段就绪；电流上限和方向必须来自已验证板级记录，不能由实施者猜测。

## 1. Current Baseline

计划编写时的事实基线：

- HEAD：`bd1012cf9c9c2e0c5a1d52b16665fe1d1728933f`。
- known-good tag：`m33-known-good-before-ble-20260710`，指向 `99721d1d`。
- 工作区包含用户的 tracked/untracked 修改；`tests/host/` 也尚未纳入版本控制。
- `main` 优先级 10；minimal 分支持续 `control_layer_poll_once()` 加 NOP spin。
- `rehab_svc` 优先级 21、目标周期 20 ms；当前没有调度保证。
- `CONTROL_CAN_RX_THREAD_ENABLE=0`；main 是当前唯一正常 CAN RX 消费者。
- `rehab_mode_manager_tick()` 为空且无调用者。
- `control_motor_current_control()` 每周期重复 run mode、2 ms delay、enable、2 ms delay 和 `iq_ref`。
- `ctrl_prearm_check_build()` 只用于诊断/状态，没有成为 mode admission；Shell 直接调用 service。
- 当前 host 算法测试可以重新编译并输出 `rehab_assist_v2_test PASS`，但它尚未覆盖 lease、prearm、调度或电机调用次数。

执行期间严禁 `git reset --hard`、`git clean`、自动 stash 或覆盖现有 untracked tests。每个任务只 stage “Files”中列出的文件。

---

### Task 1: Freeze The Dirty Baseline And Make Firmware Identity Verifiable

**Files:**

- Create: `tools/test_m33_firmware_manifest.py`
- Create: `tools/m33_firmware_manifest.py`
- Create: `applications/common/firmware_identity.h`
- Create: `applications/common/firmware_identity.c`
- Modify: `SConstruct`
- Modify: `applications/main.c`
- Output, do not commit as source: `artifacts/firmware/m33-gate0-baseline/manifest.json`

- [ ] **Step 1: Capture the protected worktree inventory**

Run:

```powershell
rtk git status --short
rtk git rev-parse HEAD
rtk git describe --always --dirty --tags
rtk git diff --check
```

Expected: HEAD matches the baseline above; dirty files are recorded, not cleaned. `git diff --check` must pass before implementation edits begin.

- [ ] **Step 2: Write failing manifest tests**

Tests must cover clean repository metadata, dirty refusal, `--allow-dirty`, missing canonical artifact, artifact tamper, config tamper, and path escape. Canonical firmware artifacts are only `rt-thread.elf`, `rtthread.map`, and `build/rtthread.hex`; `Debug/rtthread.hex` must be rejected.

Run:

```powershell
rtk python -m unittest tools.test_m33_firmware_manifest -v
```

Expected before implementation: import failure or missing manifest behavior.

- [ ] **Step 3: Implement firmware identity injection**

In `SConstruct`, before `PrepareBuilding(...)`, obtain full Git SHA and dirty flag with argument-list `subprocess` calls and append quoted `FW_GIT_SHA`, numeric `FW_GIT_DIRTY`, and a short config digest define. Do not inject `__DATE__`/`__TIME__` as the release identity.

`firmware_identity.c` must expose:

```c
typedef struct
{
    const char *git_sha;
    rt_bool_t dirty;
    const char *config_digest;
} firmware_identity_t;

void firmware_identity_get(firmware_identity_t *out);
```

Add `fw_info` as a read-only MSH command and print the same identity once during boot. If SCons did not provide the defines, report `unknown` and `releasable=0`; never fabricate a SHA.

- [ ] **Step 4: Implement manifest create/verify**

The JSON must include schema version, branch, full HEAD, dirty/releasable flags, tracked diff hash, each untracked path/size/hash, `rtconfig.h`, `applications/control/control_layer_cfg.h`, the selected `config/motion_profiles/*.h`, `board/linker_scripts/link.ld` hashes, tool versions, and artifact SHA-256/size. Before Task 4 introduces profile selection, record `motion_profile=legacy-inline` plus the central config hash; after Task 4, a missing selected-profile hash is a verification failure. Do not store file contents or credentials.

`create` must refuse a dirty release unless `--allow-dirty` is present. `verify` must recompute every hash and confirm the full SHA string exists in both ELF bytes and decoded Intel HEX payload.

- [ ] **Step 5: Run tests, build, and capture the diagnostic baseline**

Run:

```powershell
rtk python -m unittest tools.test_m33_firmware_manifest -v
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4
rtk python tools/m33_firmware_manifest.py create --output artifacts/firmware/m33-gate0-baseline --allow-dirty
rtk python tools/m33_firmware_manifest.py verify --manifest artifacts/firmware/m33-gate0-baseline/manifest.json
```

Expected: tests pass, SCons prints `done building targets`, manifest verifies, and `releasable=false` because the current worktree is dirty.

- [ ] **Step 6: Review and commit only identity tooling**

```powershell
rtk git diff --check
rtk git diff -- SConstruct applications/main.c applications/common/firmware_identity.c applications/common/firmware_identity.h tools/m33_firmware_manifest.py tools/test_m33_firmware_manifest.py
rtk git add SConstruct applications/main.c applications/common/firmware_identity.c applications/common/firmware_identity.h tools/m33_firmware_manifest.py tools/test_m33_firmware_manifest.py
rtk git commit -m "feat(m33): add traceable firmware identity"
```

Expected: no unrelated user files are staged.

### Task 2: Add Fixed-Memory Runtime Metrics Without A Monitor Thread

**Files:**

- Review and add, preserving existing content: `tests/host/rtthread.h`
- Review and add, preserving existing content: `tests/host/rehab_host_preinclude.h`
- Review and add, preserving existing content: `tests/host/rehab_assist_v2_test.c`
- Create: `tools/run_m33_gate01_host_tests.py`
- Create: `applications/common/runtime_metrics.h`
- Create: `applications/common/runtime_metrics.c`
- Create: `tests/host/runtime_metrics_test.c`
- Create: `tools/test_m33_observability_static.py`
- Modify: `applications/main.c`
- Modify: `applications/control/rehab_service.c`
- Modify: `applications/m33/m55_emg_stream_bridge.c`
- Modify later in Task 6: `applications/control/control_layer.c`

- [ ] **Step 1: Preserve and rerun the existing untracked assist test**

Before adding any new host source, inspect the existing three files above and run the exact baseline compile from Task 4. Expected: `rehab_assist_v2_test PASS`. If content differs from the reviewed baseline, stop and reconcile rather than overwriting it.

```powershell
rtk gcc -std=c11 -Wall -Wextra -Werror -Itests\host -Iapplications\control -include tests\host\rehab_host_preinclude.h tests\host\rehab_assist_v2_test.c applications\control\rehab_assist_strategy.c applications\control\rehab_adaptive_pid.c applications\control\rehab_adrc.c applications\control\rehab_active_follow.c -lm -o tmp\rehab_assist_v2_test.exe
rtk tmp\rehab_assist_v2_test.exe
```

- [ ] **Step 2: Create the source-building host runner**

The runner owns an explicit test-to-source matrix, always compiles into `tmp/gate01-host/` with `-Wall -Wextra -Werror`, prints every compile/run command, and never accepts an existing `.exe` as evidence. Initialize its matrix with `rehab_assist_v2_test` and `runtime_metrics_test`; every later task that creates a host test must update this matrix in the same commit.

- [ ] **Step 3: Write failing histogram and static wiring tests**

Cover tick wrap, start/finish pairing, max interval, max body time, overrun count, histogram quantiles, reset, and an unfinished cycle. The static test must require probes in `m33_ipc_pump_entry`, `rehab_service_worker`, `m55_emg_stream_entry`, and the current active CAN RX owner.

Run:

```powershell
rtk gcc -std=c11 -Wall -Wextra -Werror -Itests\host -Iapplications\common tests\host\runtime_metrics_test.c applications\common\runtime_metrics.c -o tmp\runtime_metrics_test.exe
rtk tmp\runtime_metrics_test.exe
rtk python -m unittest tools.test_m33_observability_static -v
```

Expected before implementation: missing header/functions and static probe failures.

- [ ] **Step 4: Implement fixed-size task metrics**

Use static storage only. Do not install a scheduler hook and do not create a metrics thread. Each slot records `start_count`, `finish_count`, `alive_seq`, last age, start-to-start P50/P95/P99/max, body P95/max, and overrun count. Use a fixed histogram rather than an unbounded sample log.

Gate 0 defaults to RT tick time and prints `clock=tick`; optional DWT support must remain compile-time disabled until Non-secure access is proven. A 1 ms clock must not be presented as microsecond precision.

Expose `rtm_show` and `rtm_reset`. The show path snapshots counters under a short critical section and prints outside it.

- [ ] **Step 5: Wire task probes and unify rehab exits**

All early exits in `rehab_service_worker()` must pass through one cycle-finalization block so `finish_count` is never skipped. Instrument the current main CAN poll in this task so Task 2 can pass. Task 5 keeps that probe unchanged; Task 6 moves the same slot to `ctrl_can_rx_entry` in the atomic ownership change.

- [ ] **Step 6: Run host/static tests and full build**

```powershell
rtk gcc -std=c11 -Wall -Wextra -Werror -Itests\host -Iapplications\common tests\host\runtime_metrics_test.c applications\common\runtime_metrics.c -o tmp\runtime_metrics_test.exe
rtk tmp\runtime_metrics_test.exe
rtk python tools/run_m33_gate01_host_tests.py
rtk python -m unittest tools.test_m33_observability_static -v
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4
```

Expected: host test prints PASS, static test passes, firmware links without shared-memory growth from this module.

- [ ] **Step 7: Commit runtime observability**

```powershell
rtk git add applications/common/runtime_metrics.c applications/common/runtime_metrics.h applications/main.c applications/control/rehab_service.c applications/m33/m55_emg_stream_bridge.c tests/host/rtthread.h tests/host/rehab_host_preinclude.h tests/host/rehab_assist_v2_test.c tests/host/runtime_metrics_test.c tools/run_m33_gate01_host_tests.py tools/test_m33_observability_static.py
rtk git commit -m "feat(m33): measure critical task runtime"
```

### Task 3: Add IPC And M55-Result Conservation Metrics Without Changing ABI

**Files:**

- Modify: `applications/common/m33_m55_comm.h`
- Modify: `applications/common/m33_m55_comm.c`
- Modify: `applications/m33/m55_model_bridge.h`
- Modify: `applications/m33/m55_model_bridge.c`
- Modify: `applications/control/can_metrics.h`
- Modify: `applications/control/can_metrics.c`
- Modify: `tools/test_m33_observability_static.py`
- Modify: `tools/m33_firmware_manifest.py`
- Modify: `tools/test_m33_firmware_manifest.py`
- Paired modify: `F:/RT-ThreadStudio/workspace/Edgi_Talk_M55_Blink_LED/applications/m33_m55_comm.h`
- Paired modify: `F:/RT-ThreadStudio/workspace/Edgi_Talk_M55_Blink_LED/applications/m33_m55_comm.c`
- Paired modify: `F:/RT-ThreadStudio/workspace/Edgi_Talk_M55_Blink_LED/SConstruct`
- Paired modify: `F:/RT-ThreadStudio/workspace/Edgi_Talk_M55_Blink_LED/applications/main.c`
- Paired create: `F:/RT-ThreadStudio/workspace/Edgi_Talk_M55_Blink_LED/applications/firmware_identity.h`
- Paired create: `F:/RT-ThreadStudio/workspace/Edgi_Talk_M55_Blink_LED/applications/firmware_identity.c`
- Output: `artifacts/firmware/m33-m55-gate0-pair/manifest.json`

- [ ] **Step 1: Extend failing static invariants**

The current ELF reports `sizeof(m33_m55_message_t) == 308`. Add a shared C/C++ compile-time assertion fixed to `308U`, and compile it on both M33 and M55 builds. The static test must require that exact value, queue depth `5`, and unchanged queue timeout expressions. It must fail if metrics fields are placed in `CY_SECTION_SHAREDMEM` or added to `m33_m55_message_t`; never regenerate the expected size from already-modified headers.

Before touching the paired M55 files, establish a clean file-level baseline:

```powershell
rtk git -C F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED status --short
rtk git -C F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED diff --check
rtk git -C F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED diff -- SConstruct applications/main.c applications/m33_m55_comm.c applications/m33_m55_comm.h
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -C F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED -j4
```

Expected: baseline M55 build passes and the four existing target files have no pre-existing content diff. If any target is already modified, stop and reconcile ownership; do not mix it into this task. Preserve every unrelated M55 change. The assertion and private metrics API must remain source-compatible on both cores.

- [ ] **Step 2: Implement private-RAM IPC counters**

Add a snapshot/reset API that records init attempt/fail stage, TX attempt/ok/full/timeout/error, RX ok/empty/error, queue high-water, last seq/type/age, seq gap/duplicate, and wrong-consumer calls. Counters live in each core's private RAM. Do not change shared data, IRQ configuration, queue depth, or timeout.

Register `m33_ipc_pump_entry` as the intended M33 RX owner after successful start. Gate 0 only reports `wrong_owner`; it does not silently reject a legacy call until all callers are inventoried.

Expose `ipcm_show` and `ipcm_reset`.

- [ ] **Step 3: Count AI result forwarding conservation**

In `m55_model_bridge_handle_ai_result()`, record `ai_rx`, `in_flight`, IPC seq gap/dup, `can_forward_ok`, `can_forward_fail`, invalid payloads, last seq, and last age. The snapshot invariant must always be:

```text
ai_rx == can_forward_ok + can_forward_fail + in_flight
```

Before CAN send, increment `ai_rx` and `in_flight` together under a short critical section. After send, decrement `in_flight` and increment exactly one outcome in another short critical section. Snapshot all four fields under the same protection; never hold it across CAN send. At quiescence, `in_flight=0` and the completed equality holds.

Validate `confidence` and `pain_risk` as finite values in their legal range before float-to-integer conversion. NaN, infinity, negative, and out-of-range payloads increment invalid/fail and are not forwarded as normal results. Protect the complete `g_m55_model_state` update/snapshot so readers cannot mix a new sequence with an old payload.

Replace the per-result unconditional `rt_kprintf` with counters plus an explicitly rate-limited diagnostic. Do not change CAN ID `0x323` or its payload in this gate.

- [ ] **Step 4: Make existing CAN counters concurrency-safe**

Use short critical sections for counter updates/snapshots and add a fixed eight-slot `CANM_TXSRC` table keyed by RT thread identity. Do not edit `drv_can.c`, TX mailbox selection, send waits, recovery, filters, CAN IDs, or DLC.

- [ ] **Step 5: Add paired M55 firmware identity and manifest verification**

Apply the Task 1 identity pattern to M55: its SConstruct injects full M55 Git SHA/dirty/config digest, boot prints it once, and the read-only command is `m55_fw_info`. Do not change the IPC message ABI to transport the SHA.

Extend `m33_firmware_manifest.py create/verify` with `--paired-m55-root F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED`. In paired mode, record M55 branch/HEAD/dirty state plus SHA-256/size of canonical `rt-thread.elf`, `rtthread.map`, and `rtthread.hex`, and verify the M55 SHA is embedded in ELF/decoded HEX. Tests cover M55 dirty refusal, tamper, stale artifact, and M33/M55 pair mismatch.

- [ ] **Step 6: Verify both working trees before commit**

```powershell
rtk python -m unittest tools.test_m33_firmware_manifest tools.test_m33_observability_static tools.test_m33_can_direct_recv_static tools.test_m33_scheduler_sram_linker_static -v
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -C F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED -j4
rtk git diff --check
rtk git -C F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED diff --check
```

- [ ] **Step 7: Commit M33 and M55 changes separately**

```powershell
rtk git add applications/common/m33_m55_comm.c applications/common/m33_m55_comm.h applications/m33/m55_model_bridge.c applications/m33/m55_model_bridge.h applications/control/can_metrics.c applications/control/can_metrics.h tools/m33_firmware_manifest.py tools/test_m33_firmware_manifest.py tools/test_m33_observability_static.py
rtk git commit -m "feat(m33): expose ipc and model forwarding metrics"
rtk git -C F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED add SConstruct applications/main.c applications/firmware_identity.c applications/firmware_identity.h applications/m33_m55_comm.c applications/m33_m55_comm.h
rtk git -C F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED commit -m "feat(m55): expose ipc transport metrics"
```

- [ ] **Step 8: Rebuild post-commit artifacts and create the paired manifest**

```powershell
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -C F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED -j4
rtk python tools/m33_firmware_manifest.py create --output artifacts/firmware/m33-m55-gate0-pair --paired-m55-root F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED --allow-dirty
rtk python tools/m33_firmware_manifest.py verify --manifest artifacts/firmware/m33-m55-gate0-pair/manifest.json
```

Expected: embedded identities match both post-commit HEADs, IPC ABI/static guards pass, and neither core's shared-memory section grows because counters are private. A dirty pair is diagnostic-only.

### Task 4: Establish Reproducible Host Tests And Fail-Closed Defaults

**Files:**

- Modify: `tools/run_m33_gate01_host_tests.py`
- Create: `tools/test_m33_gate01_static.py`
- Modify: `tools/test_rehab_mode_static.py`
- Modify: `applications/control/control_layer_cfg.h`
- Modify: `SConstruct`
- Create: `applications/control/control_motion_gate.h`
- Create: `applications/control/control_motion_gate.c`
- Create: `tests/host/control_motion_gate_test.c`
- Modify: `applications/control/control_layer.c`
- Modify: `applications/control/control_layer.h`
- Create: `config/motion_profiles/README.md`
- Create: `config/motion_profiles/m33_safe.h`
- Create: `config/motion_profiles/m33_gate01_faultinj.h`
- Modify: `tools/m33_firmware_manifest.py`
- Modify: `tools/test_m33_firmware_manifest.py`

- [ ] **Step 1: Re-run the protected existing host test before editing it**

```powershell
rtk gcc -std=c11 -Wall -Wextra -Werror -Itests\host -Iapplications\control -include tests\host\rehab_host_preinclude.h tests\host\rehab_assist_v2_test.c applications\control\rehab_assist_strategy.c applications\control\rehab_adaptive_pid.c applications\control\rehab_adrc.c applications\control\rehab_active_follow.c -lm -o tmp\rehab_assist_v2_test.exe
rtk tmp\rehab_assist_v2_test.exe
```

Expected baseline: `rehab_assist_v2_test PASS`. If the existing untracked file differs, stop and review rather than replacing it.

- [ ] **Step 2: Write a unified host runner and failing safe-default assertions**

Confirm the runner still compiles from source into `tmp/gate01-host/`, uses `-Wall -Wextra -Werror`, prints every compile/run command, and returns nonzero on the first failure. It must not accept a prebuilt `.exe` as evidence. Add any Task 2 tests that are not yet in its explicit matrix. Give it an optional `--profile <stem>` argument that uses the same canonical resolution rules as SConstruct, preprocesses a contract probe with that header forcibly included, and prints the resolved macro values plus profile digest before running tests. An invalid contract returns nonzero.

The new static test must initially fail on these required defaults:

```c
CONTROL_DEVELOPMENT_BENCH_MOTION_ENABLE == 0U
CONTROL_CLINICAL_MOTION_ENABLE == 0U
CONTROL_ROS_COMMAND_LOGGING_ONLY == 1U
CONTROL_REHAB_BENCH_MAX_CURRENT_A == 0.0f
CONTROL_REHAB_MULTI_JOINT_ASSIST_ENABLE == 0U
CONTROL_RAW_MOTION_SHELL_ENABLE == 0U
CONTROL_LEGACY_MOTION_API_ENABLE == 0U
```

Remove the old static assertions that forced `bench=1` and `logging_only=0`.

- [ ] **Step 3: Make profile selection reproducible and default-safe**

Add `config/motion_profiles/m33_safe.h` with `CONTROL_REHAB_BENCH_MAX_CURRENT_A=0.0f`, bench off, clinical off, multi-joint assist off, and unvalidated torque signs zero. Add `m33_gate01_faultinj.h` with the same no-motion values plus `CONTROL_GATE01_FAULT_INJECTION_ENABLE=1`.

`SConstruct` accepts a profile stem, with `M33_MOTION_PROFILE=m33_safe` as the default; it rejects absolute paths, `..`, missing files, and profiles outside `config/motion_profiles/`. It resolves one canonical header before `PrepareBuilding(...)` and globally appends GCC `-include` followed by that canonical header path, so profile macros are visible before `control_layer_cfg.h` defaults in every translation unit. It also injects the selected profile name/digest into firmware identity. Do not merely add the header to `CPPPATH` or source lists; that does not include it.

A future validated bench build uses the committed board-specific header `m33_bench_pse84_eval_epc2_lab1.h`; it must not edit `m33_safe.h` or change the default. The manifest records the selected name and hash. Do not place a guessed nonzero current in any profile.

Extend the Task 1 manifest tests/tool in this same step: `legacy-inline` remains valid only for historical Gate 0 artifacts, while every newly built Gate 1 artifact must name and hash a committed selected profile. Verification rejects a profile-name/hash mismatch.

`config/motion_profiles/README.md` and host/preprocessor tests must enforce this truth table:

| Profile | Bench | Clinical | ROS logging-only | Cap | Multi-joint | Raw/legacy motion Shell/API | Fault injection |
|---|---:|---:|---:|---:|---:|---:|---:|
| `m33_safe` | 0 | 0 | 1 | 0 A | 0 | 0 | 0 |
| `m33_gate01_faultinj` | 0 | 0 | 1 | 0 A | 0 | 0 | 1 |
| `m33_bench_pse84_eval_epc2_lab1` | 1 | 0 | 0 | signed approved record | 0 | 0 | 0 |

For the lab profile, exactly one requested motor4/5/6 torque sign is `+1.0f` or `-1.0f`; all unvalidated signs remain zero. CAN-owned bench motion requires heartbeat and logging-only clear. Local Shell-owned bench motion does not require NanoPi heartbeat, but it still requires bench enable, single-joint mask, calibration, fresh/fault-free feedback, valid sign, approved cap, and external physical cutoff. Clinical is not enabled in this gate.

Use preprocessor/SCons dry-run tests to prove default-safe, explicit fault-injection, missing-profile, path-traversal, and absolute-path behavior; use a temporary unit-test fixture to exercise a syntactically valid bench selection without committing physical values. The runner's `--profile` path must share this tested resolver/contract code rather than reimplement it. When the real lab profile is created in Stage C, rerun the same macro/digest contract against that file before commit.

Keep `CONTROL_PREARM_*_CONFIRMED` and `*_SAFE_NOW` at zero. Keep clinical disabled. Keep the assist group definition `0x38`, but reject multi-joint current modes while `CONTROL_REHAB_MULTI_JOINT_ASSIST_ENABLE=0`.

- [ ] **Step 4: Enforce the safe profile at every motion-producing API boundary**

`CONTROL_ROS_COMMAND_LOGGING_ONLY` protects only the ROS command path and is not a global motor gate. Add a pure `control_motion_gate` action policy and table-driven host tests. In `m33_safe`, deny enable, zero calibration, run-mode changes, generic parameter writes, MIT/nonzero-current/speed/position commands, CANSimple position/velocity/nonzero-torque commands, and compatibility joint targets. Always allow read/probe/status/active-report telemetry, a setpoint-only `0.0f` current write, and STOP/disable. The legacy `control_motor_current_control(0)` is still denied because it enables the drive before writing zero.

Every listed public API must call the common gate before constructing or sending a motion frame; checking only Shell commands is insufficient. Compile all raw motion-producing MSH commands out unless `CONTROL_RAW_MOTION_SHELL_ENABLE=1` in a separately reviewed profile. Add a static call-site inventory so a newly exported raw motion command fails CI until classified.

Add a narrow `control_motor_current_zero()` that only writes zero IQ and never changes mode/enables. After CAN initialization, every profile seeds a per-joint pending mask for zero/STOP. A nonblocking `control_safe_stop_tick(now)` attempts at most one due joint per call, clears a joint only after the required sends are driver-accepted, and retries failures with bounded low-frequency backoff. Until the pending mask is zero, every profile rejects prepare/nonzero output; the safe profile never opens motion afterward. Call the tick from the current main poll/health path in Task 4, retain it through phase A, and keep it in the p25 health loop after Task 6. This covers an M33 reset while a drive retained an earlier state without flooding an already-unstable startup bus. No safety mutex may be held across a send.

Expose pending mask, attempt/failure count, last result, and age. While pending is nonzero, status is `SAFE_STOP_PENDING`; no nonzero action is permitted. Add host tests for partial success, tick wrap, backoff, one-joint-per-call budgeting, and permanent failure without nonzero output.

At this stage bench/clinical action policy may admit motion only at the coarse profile level; Tasks 8-10 add per-request prearm and generation-bound rehab authorization. The final static gate must ensure no current-mode caller bypasses that authorization.

- [ ] **Step 5: Verify the safe image**

```powershell
rtk python tools/run_m33_gate01_host_tests.py
rtk python -m unittest tools.test_m33_gate01_static -v
rtk python -m unittest tools.test_m33_firmware_manifest -v
rtk python tools/test_rehab_mode_static.py
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4
```

Expected: all tests pass and `fw_info` for this artifact will report a non-motion safe profile.

- [ ] **Step 6: Commit the safety baseline separately**

```powershell
rtk git add tools/run_m33_gate01_host_tests.py tools/test_m33_gate01_static.py tools/test_rehab_mode_static.py tools/m33_firmware_manifest.py tools/test_m33_firmware_manifest.py applications/control/control_motion_gate.c applications/control/control_motion_gate.h applications/control/control_layer.c applications/control/control_layer.h applications/control/control_layer_cfg.h tests/host/control_motion_gate_test.c SConstruct config/motion_profiles/README.md config/motion_profiles/m33_safe.h config/motion_profiles/m33_gate01_faultinj.h
rtk git commit -m "safety(m33): default motion paths to fail closed"
```

### Task 5: Scheduler Rescue Phase A - Add One Real Tick Of Blocking, Keep Main As RX Owner

**Files:**

- Modify: `applications/main.c`
- Modify: `tools/test_m33_gate01_static.py`
- Output: `docs/qa/m33-gate01/scheduler-phase-a.txt`

This is an intentionally temporary, separately verifiable commit. Do not combine it with priority changes, CAN RX migration, assist algorithm changes, or motor APIs.

- [ ] **Step 1: Add the phase-A failing assertion**

Require the minimal loop to retain exactly one call to `control_layer_poll_once()` and to execute `rt_thread_mdelay(M33_MINIMAL_POLL_PERIOD_MS)` where the period is at least one tick. Forbid `rt_thread_yield()` as the starvation fix because yield only helps equal-priority threads.

- [ ] **Step 2: Replace the NOP spin with a true 1 ms block**

Keep main as the only CAN RX owner in this phase. Do not enable `CONTROL_CAN_RX_THREAD_ENABLE` yet.

- [ ] **Step 3: Run tests and build**

```powershell
rtk python -m unittest tools.test_m33_gate01_static tools.test_m33_observability_static -v
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4
```

- [ ] **Step 4: Commit phase A before hardware verification**

```powershell
rtk git add applications/main.c tools/test_m33_gate01_static.py
rtk git commit -m "fix(m33): let lower priority services run"
```

- [ ] **Step 5: Rebuild and identify the post-commit artifact**

```powershell
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4
rtk python tools/m33_firmware_manifest.py create --output artifacts/firmware/m33-gate01-phase-a --paired-m55-root F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED --allow-dirty
rtk python tools/m33_firmware_manifest.py verify --manifest artifacts/firmware/m33-gate01-phase-a/manifest.json
```

Expected: embedded SHA is the phase-A commit. Because unrelated user changes may still exist, this remains a diagnostic artifact with `releasable=false`.

- [ ] **Step 6: Verify only with motor power physically disabled**

After flashing the exact manifest artifact, collect:

```text
fw_info
rtm_reset
canm_reset 1000000
canm_default
list thread
list memheap
rtm_show
canm_show
canm_ids
```

Expected after 60 seconds: `rehab_svc` start/finish counters advance, main spends time suspended, CAN RX counters continue advancing, no nonzero motor command is possible in the safe profile, and there is no HardFault. Save the raw console output to the stated QA file. If CAN RX stops, revert this phase via Git and diagnose before Task 6.

- [ ] **Step 7: Commit the exact phase-A evidence**

```powershell
rtk git add docs/qa/m33-gate01/scheduler-phase-a.txt
rtk git commit -m "test(m33): record scheduler phase-a evidence"
```

### Task 6: Scheduler Rescue Phase B - Move CAN RX Ownership Atomically

**Files:**

- Modify: `applications/control/control_layer_cfg.h`
- Modify: `applications/control/control_layer.c`
- Modify: `applications/control/control_layer.h`
- Modify: `applications/main.c`
- Modify: `tools/test_m33_gate01_static.py`
- Modify: `tools/test_m33_observability_static.py`
- Output: `docs/qa/m33-gate01/can-rx-owner-phase-b.txt`

- [ ] **Step 1: Write final single-owner static assertions**

Require:

- `CONTROL_CAN_RX_THREAD_ENABLE=1`.
- `CONTROL_CAN_RX_POLL_PERIOD_MS=1` for the direct-PDL migration baseline.
- Minimal main contains no `control_layer_poll_once()`.
- `cmd_control_poll`, `cmd_motor_probe_last`, and `cmd_m33_prearm_check` do not drain FIFO.
- `ctrl_poll_can_messages()` is only called inside `ctrl_can_rx_entry()`; the two compile-time branches count as the same owner.
- `CONTROL_ROS_CMD_THREAD_ENABLE` remains off because there is currently no `rt_mq_send` producer.

- [ ] **Step 2: Make the ownership change in one commit-sized edit**

Enable `ctrl_can`, replace its hard-coded 10 ms direct-PDL sleep with the 1 ms config value, remove `control_layer_poll_once()` from public API, and turn `cmd_control_poll` into a read-only RX-owner diagnostic or remove it. Probe/prearm commands must read caches only.

After successful initialization, lower the existing main thread from priority 10 to `M33_HEALTH_THREAD_PRIORITY=25`; retain it only as a 500 ms LED/health loop. This avoids adding another thread and prevents a periodically waking p10 main from injecting control jitter.

Move the runtime CAN slot from main to `ctrl_can_rx_entry`. Record poll count, maximum poll gap, drained frames, drain-limit hits, and last alive tick. Keep CAN feedback parsing priority 18 above rehab priority 21.

- [ ] **Step 3: Verify static/host/build gates**

```powershell
rtk python -m unittest tools.test_m33_gate01_static tools.test_m33_observability_static tools.test_m33_can_direct_recv_static -v
rtk python tools/run_m33_gate01_host_tests.py
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4
rtk git diff --check
```

- [ ] **Step 4: Commit the atomic migration**

```powershell
rtk git add applications/control/control_layer_cfg.h applications/control/control_layer.c applications/control/control_layer.h applications/main.c tools/test_m33_gate01_static.py tools/test_m33_observability_static.py
rtk git commit -m "fix(m33): assign can rx to one worker"
```

- [ ] **Step 5: Rebuild and identify the post-commit phase-B artifact**

```powershell
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4
rtk python tools/m33_firmware_manifest.py create --output artifacts/firmware/m33-gate01-phase-b --paired-m55-root F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED --allow-dirty
rtk python tools/m33_firmware_manifest.py verify --manifest artifacts/firmware/m33-gate01-phase-b/manifest.json
```

Only this post-commit verified artifact may be flashed for the phase-B test.

- [ ] **Step 6: Verify disconnected and loaded CAN behavior**

With motor output still disabled, run a 30-minute normal traffic capture, then the highest existing F103/telemetry traffic profile. Required evidence:

- `ctrl_can` alive counter advances continuously.
- main is delay/suspend at priority 25.
- `rehab_svc` still advances.
- FIFO lost/full, drain-limit, bus-off, and unexpected sequence loss remain zero.
- Existing `0x321 -> 0x322`, F103 sensor/ACK, motor feedback, and M55 result RX still arrive.

If drain-limit or FIFO loss appears, do not raise queue sizes blindly. Record arrival rate and shorten the poll/budget only after measurement.

- [ ] **Step 7: Commit the exact phase-B evidence**

```powershell
rtk git add docs/qa/m33-gate01/can-rx-owner-phase-b.txt
rtk git commit -m "test(m33): record can rx owner evidence"
```

### Task 7: Make Initialization Single-Owner And Rollback-Safe

**Files:**

- Modify: `applications/control/rehab_service.h`
- Modify: `applications/control/rehab_service.c`
- Modify: `applications/control/rehab_shell.c`
- Modify: `applications/control/rehab_mode_manager.h`
- Modify: `applications/control/rehab_mode_manager.c`
- Modify: `applications/control/control_layer.c`
- Modify: `applications/control/rehab_shell.c`
- Create: `tests/host/rehab_init_state_test.c`
- Modify: `tools/run_m33_gate01_host_tests.py`

- [ ] **Step 1: Write failing init-state tests**

Cover `UNINIT -> STARTING -> READY`, create failure to `FAILED`, startup failure rollback, repeated init, command before READY, status before READY, and explicit shutdown cleanup. Verify no second mutex/thread/MQ is created.

- [ ] **Step 2: Split create/start and remove lazy initialization**

Use a small explicit state enum in service and manager. `control_layer_init()` is the sole boot owner:

1. initialize manager lock and lifecycle state;
2. create service mutex/thread in PASSIVE without starting it;
3. finish CAN/control objects;
4. start CAN and service threads, checking every `rt_thread_startup()` result;
5. publish READY only after all required owners are alive.

On failure, delete created threads, detach MQ/mutex/sem objects, clear handles, and leave motion fail closed. `rehab_mode_manager_init()` must not call service init. Shell/status/heartbeat paths must return not-ready or a zeroed diagnostic; they must not run `memset` or create kernel objects.

- [ ] **Step 3: Run host/static/build tests**

```powershell
rtk python tools/run_m33_gate01_host_tests.py
rtk python -m unittest tools.test_m33_gate01_static -v
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4
```

- [ ] **Step 4: Commit init lifecycle separately**

```powershell
rtk git add applications/control/rehab_service.c applications/control/rehab_service.h applications/control/rehab_mode_manager.c applications/control/rehab_mode_manager.h applications/control/control_layer.c applications/control/rehab_shell.c tests/host/rehab_init_state_test.c tools/run_m33_gate01_host_tests.py
rtk git commit -m "fix(m33): make rehab initialization transactional"
```

### Task 8: Introduce A Pure Prearm Policy And Fail-Closed Bench/Clinical Rules

**Files:**

- Create: `applications/control/control_prearm.h`
- Create: `applications/control/control_prearm.c`
- Create: `tests/host/control_prearm_test.c`
- Modify: `applications/control/control_layer.h`
- Modify: `applications/control/control_layer.c`
- Modify: `applications/control/control_layer_cfg.h`
- Modify: `config/motion_profiles/m33_safe.h`
- Modify: `applications/control/rehab_mode_manager.c`
- Modify: `applications/control/rehab_service.c`
- Modify: `tools/test_m33_gate01_static.py`
- Modify: `tools/run_m33_gate01_host_tests.py`

- [ ] **Step 1: Write table-driven failing prearm tests**

Start from one fully valid synthetic snapshot, then flip exactly one condition per case: safe profile, unsupported mask, zero mask, multi-joint disabled, uncalibrated bit, stale bit, motor fault bit, invalid torque sign bit, zero/negative cap, remote logging-only, missing CAN heartbeat, heartbeat over boundary, estop, power, limits, and clinical disabled. Assert both deterministic primary `detail` and the complete `failure_mask`.

Also test:

- STOP is allowed for every profile and source.
- Bench local Shell does not require NanoPi heartbeat but still requires a single requested joint, calibration, fresh feedback, zero `fault_summary`, valid direction, and a nonzero validated cap.
- CAN motion requires heartbeat and logging-only clear in both bench and clinical modes; local bench Shell does not consume the ROS logging-only bit.
- Clinical additionally requires all physical confirmations and safe-now values.
- Effective cap equals `min(strategy_cap, motor_cap, profile_cap)`.

- [ ] **Step 2: Implement pure evaluation and one runtime snapshot collector**

The pure API must have no CAN, mutex, tick, or shell dependency:

```c
void control_prearm_evaluate(const control_prearm_input_t *input,
                             control_prearm_result_t *result);
```

Add `control_get_motor_feedback_snapshot()` to copy all feedback under `s_data_lock` once. Build the runtime input after releasing that lock. Add calibrated/fresh/fault/direction-valid masks and a specific reject detail; do not collapse every failure into `MOTOR_FAULT`.

Evaluate every condition without early return and return a stable bitwise `failure_mask`; `detail` is only the deterministic highest-priority summary. This allows a safe/cap-zero validation image to expose stale, fault, sign, and mask failures simultaneously instead of hiding them behind the first failure.

Move the existing `m33_prearm_check` output onto this same evaluator. Delete `ctrl_prearm_check_build()` after all callers migrate; do not keep two safety implementations.

- [ ] **Step 3: Define direction and cap configuration without guessing**

Replace the unused/incomplete `JOINT0..4_TORQUE_SIGN` set with explicit M33 motor-joint 1..7 entries. Unvalidated assist joints default to `0.0f`, which prearm treats as invalid. A board validation record must set a requested assist joint to exactly `+1.0f` or `-1.0f`.

The repository bench current cap remains zero. A nonzero cap may only be supplied by a reviewed board profile and must appear in `fw_info`/manifest config digest.

- [ ] **Step 4: Run policy and architecture tests**

```powershell
rtk python tools/run_m33_gate01_host_tests.py
rtk python -m unittest tools.test_m33_gate01_static -v
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4
```

- [ ] **Step 5: Commit the single prearm implementation**

```powershell
rtk git add applications/control/control_prearm.c applications/control/control_prearm.h applications/control/control_layer.c applications/control/control_layer.h applications/control/control_layer_cfg.h config/motion_profiles/m33_safe.h applications/control/rehab_mode_manager.c applications/control/rehab_service.c tests/host/control_prearm_test.c tools/test_m33_gate01_static.py tools/run_m33_gate01_host_tests.py
rtk git commit -m "safety(m33): unify rehab prearm admission"
```

### Task 9: Route CAN And Shell Through One Bounded Rehab Command Broker

**Files:**

- Create: `applications/control/rehab_command_policy.h`
- Create: `applications/control/rehab_command_policy.c`
- Create: `tests/host/rehab_command_policy_test.c`
- Modify: `applications/control/rehab_mode_manager.h`
- Modify: `applications/control/rehab_mode_manager.c`
- Modify: `applications/control/rehab_service.h`
- Modify: `applications/control/rehab_service.c`
- Modify: `applications/control/rehab_shell.c`
- Modify: `applications/control/control_layer.c`
- Modify: `applications/control/control_motion_gate.h`
- Modify: `applications/control/control_motion_gate.c`
- Modify: `tools/test_m33_gate01_static.py`
- Modify: `tools/run_m33_gate01_host_tests.py`

- [ ] **Step 1: Write failing lease and queue tests**

Use the pure `rehab_command_policy` module to cover no heartbeat, exact TTL boundary, TTL+1 expiry, unsigned tick wrap, renewal, expiry latched once, heartbeat recovery without mode recovery, source ownership conflict, idempotent duplicate request, stale epoch drop, and STOP from every source/state. Do not mock the whole RT-Thread kernel. Queue-full and urgent-latch integration are verified by static checks and Stage B board fault injection.

Required STOP behavior:

- increments command epoch;
- sets a dedicated `stop_pending` latch before attempting queue insertion;
- invalidates all older queued motion requests;
- is checked again immediately before every subsequent control-cycle nonzero setpoint;
- remains observable even when the normal queue is full.

- [ ] **Step 2: Add a fixed queue without adding a manager thread**

Use a fixed depth-eight `rt_mq` owned by `rehab_mode_manager`, consumed only by the existing `rehab_svc` worker at the start of each 20 ms cycle. Do not enable the dead ROS MQ thread and do not add a soft timer.

Extend Task 7's transactional lifecycle so MQ creation failure rolls back and shutdown detaches the MQ. Do not reintroduce lazy init.

Add a trusted-source API; source is supplied by the internal caller, never accepted from CAN payload data:

```c
rt_err_t rehab_mode_manager_submit(const rehab_mode_command_t *cmd,
                                   rehab_cmd_source_t source,
                                   rt_uint32_t *out_request_id);
rt_err_t rehab_mode_manager_submit_stop(rehab_cmd_source_t source,
                                        rt_uint8_t sequence,
                                        rt_uint8_t detail,
                                        rt_uint32_t *out_request_id);
```

Allocate request IDs under the queue-state lock. Set `out_request_id` only after a successful enqueue/latch; queue failure must never print `queued`. Keep `rehab_mode_manager_apply_command()` as the CAN wrapper if protocol compatibility requires it, but it must only validate/queue. It must not call motor/service transition functions synchronously.

- [ ] **Step 3: Execute mode changes only in `rehab_svc`**

At each release, the service worker processes `stop_pending`, drops stale epochs, runs the common prearm check against a fresh snapshot, and only then applies a request. Store owner only after successful transition. Same-source/same-mode/same-mask requests are idempotent and must not re-arm.

Duplicate comparison uses the full normalized request: source, mode, submode, mask, bounded velocity, bounded threshold, and every other supported session field. If mode/mask are unchanged but parameters differ while ACTIVE, reject with `-RT_EBUSY` and require PASSIVE before applying the new parameters; do not silently call it idempotent and do not re-arm for an in-place update.

For a non-PASSIVE CAN `SET_MODE`, map `control_ros_command_t.joint_id` through the existing ROS-to-M33 mapping and construct exactly one motor bit; verify that bit belongs to the assist-supported `0x38` group. PASSIVE/STOP is an urgent exception: ignore stale, unknown, or unsupported joint and motion parameter fields and latch STOP before any mapping or prearm validation. Do not keep hard-coding the whole `0x38` mask, and do not alias `joint_id` into the status sequence. The broker-generated request ID is the command correlation value. Add host/static cases for every mapped motion joint, unknown motion joint, motor3 motion exclusion, single-joint-only policy, and STOP carrying an invalid joint ID. This makes NanoPi and Shell use the same single-joint admission without changing the existing CAN frame layout.

Pass the expected command epoch into the actuation path. Immediately before each nonzero low-level setpoint enqueue, re-read epoch and `stop_pending`; on mismatch, skip the nonzero command and run zero+stop. Clear `stop_pending` only after zero+stop completes and PASSIVE is published. Since CAN TX is not yet a single owner, one driver send that was already in progress when STOP arrived cannot be retroactively canceled; count that case as `tx_inflight_at_stop` and verify its bounded completion. Do not claim stronger ordering until the next `can_service` gate.

Submitting STOP must also revoke the current `control_motion_gate` generation using a short, nonblocking state update. Revocation performs no CAN I/O. This gives the low-level nonzero-current API a second check even if the service worker has not reached its next release; zero current and STOP remain allowed after revocation.

Introduce the gate generation/revoke state and API in this task, and list it in the host/static tests. Task 10 consumes that generation through `control_motion_authority_t`; do not leave Task 9 calling a not-yet-defined API.

`rehab_mode_manager_tick(now)` must become real, be called once per service cycle, and emit one heartbeat-timeout STOP for an active CAN-owned mode. It must not call CAN or motor APIs and must not hold its lock while stopping.

Reject unsupported command fields explicitly. In this gate, nonzero `assist_direction_mask` is rejected until protocol semantics are defined; `max_velocity_rad_s` and assist enter threshold are copied into bounded per-session parameters rather than silently ignored.

- [ ] **Step 4: Close the Shell bypass**

`rehab active/assist/resist/record/play/stop` must construct a request and call the manager. `rehab cfg` is allowed only in PASSIVE. The command prints `queued request_id=...`; final acceptance is read from `rehab status`, so enqueue success is never reported as motor motion success.

When `CONTROL_GATE01_FAULT_INJECTION_ENABLE=1`, add `rehab_faultinj queue_full`, `rehab_faultinj invalid_source`, and `rehab_faultinj clear`. The Finsh p8 command fills the depth-eight queue before p21 can drain it, verifies the ninth submit fails and STOP still latches, then returns; all injected requests remain non-motion under the fault-injection profile. These hooks must not compile in safe, lab bench, or clinical profiles.

Remove public direct-mode mutation APIs from `rehab_service.h` once all internal callers are migrated. Keep only init/start/status/parameter and broker-consumer interfaces.

- [ ] **Step 5: Add broker diagnostics**

Expose owner, epoch, queue depth/high-water/drop, stale-drop, source-conflict, lease age, lease expiry count, last request ID, and last final result in `rehab status`. Counters update in fixed memory and printing occurs only on Shell request.

- [ ] **Step 6: Verify and commit**

```powershell
rtk python tools/run_m33_gate01_host_tests.py
rtk python -m unittest tools.test_m33_gate01_static -v
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4
rtk git diff --check
rtk git add applications/control/rehab_command_policy.c applications/control/rehab_command_policy.h applications/control/rehab_mode_manager.c applications/control/rehab_mode_manager.h applications/control/rehab_service.c applications/control/rehab_service.h applications/control/rehab_shell.c applications/control/control_motion_gate.c applications/control/control_motion_gate.h applications/control/control_layer.c tests/host/rehab_command_policy_test.c tools/test_m33_gate01_static.py tools/run_m33_gate01_host_tests.py
rtk git commit -m "feat(m33): serialize rehab mode requests"
```

### Task 10: Split One-Time Current Arming From Periodic Setpoints

**Files:**

- Create: `applications/control/rehab_motor_session.h`
- Create: `applications/control/rehab_motor_session.c`
- Create: `tests/host/rehab_motor_session_test.c`
- Modify: `applications/control/control_layer.h`
- Modify: `applications/control/control_layer.c`
- Modify: `applications/control/control_motion_gate.h`
- Modify: `applications/control/control_motion_gate.c`
- Modify: `applications/control/control_layer_cfg.h`
- Modify: `applications/control/rehab_service.h`
- Modify: `applications/control/rehab_service.c`
- Modify: `tools/test_m33_gate01_static.py`
- Modify: `tools/run_m33_gate01_host_tests.py`

- [ ] **Step 1: Write a fake-motor failing test**

With a small `rehab_motor_ops_t` fake, verify:

- prepare/run-mode/enable occurs exactly once per successful mode generation;
- periodic CURRENT output only invokes setpoint;
- forged tokens, copied tokens reused after generation rotation, and revoked tokens cannot prepare or emit nonzero current;
- a stale/revoked authority cannot emit nonzero current, while zero current and STOP remain allowed;
- NaN/infinite current or cap is rejected before CAN encoding and forces the logical stop path;
- strategy STOP writes `0.0f` but does not disable;
- repeated identical mode requests do not re-arm;
- partial multi-joint prepare failure stops already prepared joints;
- feedback stale, motor fault, lease expiry, explicit STOP, and output failure each create one logical stop transition;
- successful zero+STOP does not chatter, but either TX failure keeps the session in STOPPING and retries with bounded backoff;
- STOPPING never emits a nonzero setpoint and never re-arms;
- a new valid generation can arm after an explicit new command.

- [ ] **Step 2: Add narrow low-level APIs and keep compatibility isolated**

```c
rt_err_t control_motor_current_prepare(const control_motion_authority_t *authority,
                                       rt_uint8_t joint_id);
rt_err_t control_motor_current_setpoint(const control_motion_authority_t *authority,
                                        rt_uint8_t joint_id,
                                        float current_a);
```

`control_motion_authority_t` is an opaque handle/token, not a public struct whose generation, joint mask, profile, or cap can be filled by a caller. The authoritative active record lives only inside `control_motion_gate.c` and binds a non-reused boot-local token/nonce to owner session, generation, selected profile digest, allowed joint mask, effective cap, and revoked state. `rehab_motor_session` obtains the token only after common prearm succeeds and revokes it on STOP/fault/expiry.

Both `prepare` and `setpoint` validate the token and owner against that internal record under a short critical section, copy the authoritative mask/cap/generation to a local snapshot, and never trust caller-supplied mask or cap fields. They recheck generation/revocation immediately before a nonzero TX. A copied token is equivalent only during its still-current owning session; generation rotation or revocation makes every stale copy invalid. Host tests must reject a forged token, a copied token reused after generation rotation, a token presented for another joint/owner, and a revoked token. `prepare` performs run-mode and enable once after validation. `setpoint` validates the absolute/effective hard limit and writes `MOTOR_PARAM_INDEX_IQ_REF`; it contains no delay and no enable. A `0.0f` setpoint and STOP remain allowed even after revocation.

Keep `control_motor_current_control()` only as a compatibility wrapper for legacy bench helpers and require `CONTROL_LEGACY_MOTION_API_ENABLE=1`; all committed safe/rehab bench profiles keep that macro zero. Statically forbid `rehab_service.c` from calling the compatibility wrapper. Implement authorized prepare through internal raw helpers rather than calling the profile-blocked public legacy enable API.

- [ ] **Step 3: Implement a small session state machine**

`rehab_motor_session` owns armed mask, generation, stop latch, effective current cap, and per-joint zero/STOP completion masks. Its state machine is `DISARMED -> ARMING -> READY -> STOPPING -> PASSIVE/FAULT`. It is not a generic service locator; it exists only to make the safety-critical motor lifecycle explicit and host-testable.

For active/assist/resist:

1. evaluate prearm;
2. prepare requested joints;
3. publish mode READY only after all prepares succeed;
4. run cycles with setpoint-only writes;
5. map disengaged strategy output to zero current;
6. on exit/fault/expiry, revoke authority and enter STOPPING once;
7. retry failed zero/STOP sends with a bounded, configurable backoff while forbidding all nonzero output;
8. publish PASSIVE/FAULT stopped only after both commands for every armed joint were accepted by the driver, or hardware feedback explicitly confirms disabled.

If confirmation never arrives, remain `STOPPING_UNCONFIRMED`, expose retry/failure/age counters, continue capped retries, and require the physical cutoff. Do not set the stopped latch merely because one send attempt failed. "Stop once" means one logical transition, not one wire attempt.

Under the no-motion fault-injection profile only, add `rehab_faultinj stopping_retry`. It runs a synthetic READY session against an in-memory fake `rehab_motor_ops_t`, injects zero/STOP failures, and verifies retry/backoff/status without calling the real CAN or bypassing the motion gate. This permits target-build state-machine validation with motor power disabled. The fake backend and hook must not compile in the lab assist profile.

Memory record never arms. Memory playback remains disabled in this gate unless it passes a separately documented trajectory prearm; do not accidentally route it into current mode.

- [ ] **Step 4: Check feedback faults, not only freshness**

Every active cycle must reject `fault_summary != 0` even when timestamp is fresh. Preserve the specific failing joint and fault detail in status.

- [ ] **Step 5: Verify and commit**

```powershell
rtk python tools/run_m33_gate01_host_tests.py
rtk python -m unittest tools.test_m33_gate01_static -v
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4
rtk git add applications/control/rehab_motor_session.c applications/control/rehab_motor_session.h applications/control/control_motion_gate.c applications/control/control_motion_gate.h applications/control/control_layer_cfg.h applications/control/control_layer.c applications/control/control_layer.h applications/control/rehab_service.c applications/control/rehab_service.h applications/control/rehab_shell.c tests/host/rehab_motor_session_test.c tools/test_m33_gate01_static.py tools/run_m33_gate01_host_tests.py
rtk git commit -m "fix(m33): arm rehab current mode once"
```

### Task 11: Make The Rehab Cycle Absolute-Time And Pass Real `dt`

**Files:**

- Create: `applications/control/rehab_schedule.h`
- Create: `applications/control/rehab_schedule.c`
- Create: `tests/host/rehab_schedule_test.c`
- Modify: `tests/host/rehab_assist_v2_test.c`
- Modify: `applications/control/rehab_assist_strategy.h`
- Modify: `applications/control/rehab_assist_strategy.c`
- Modify: `applications/control/rehab_strategy.h`
- Modify: `applications/control/rehab_service.c`
- Modify: `applications/control/rehab_shell.c`
- Modify: `applications/control/control_layer_cfg.h`
- Modify: `tools/run_m33_gate01_host_tests.py`

- [ ] **Step 1: Extend failing algorithm tests**

Add enter/exit equality boundaries, hysteresis chatter, positive/negative torque, positive/negative velocity fallback, saturation, current direction, rate-based slew at 10/20/40 ms, PID integral dependence on `dt`, and invalid `dt` handling. Explicitly cover NaN/infinite torque, velocity, current cap, strategy output, and `dt`; none may pass comparisons or reach CAN encoding, and each must produce zero+fault.

- [ ] **Step 2: Change strategy APIs to accept measured `dt_s`**

Pass `dt_s` from the service into assist PID and ADRC. Replace `assist_slew_current_a_per_step` with an A/s rate and compute `max_delta = rate * dt_s`; update Shell names/status so the unit is not ambiguous.

Use the validated per-M33-joint torque sign from prearm configuration. Keep physical sensor sign separate from `follow_direction`; never allow a remote command to redefine sensor polarity.

- [ ] **Step 3: Implement a pure schedule decision and one `delay_until` cycle tail**

Put wrap-safe interval validation, release-late detection, and controller-reset decisions in `rehab_schedule.c` so `rehab_schedule_test.c` exercises production logic without mocking RT-Thread. The worker must have one absolute release point and one delay call.

Measure start-to-start interval and body time. If body time reaches/exceeds the period, increment deadline miss, immediately issue a zero setpoint after detecting the overrun, reset controller state, and resynchronize using RT-Thread's documented `rt_thread_delay_until()` behavior. Do not claim the overrun was known before the body executed.

If the observed interval is zero, invalid, or exceeds `CONTROL_REHAB_FEEDBACK_FRESH_MS`, reset controller state and output zero instead of integrating through the gap. Do not hide overruns by substituting a fixed 20 ms value.

- [ ] **Step 4: Verify all host tests and firmware**

```powershell
rtk python tools/run_m33_gate01_host_tests.py
rtk python -m unittest tools.test_m33_gate01_static tools.test_m33_observability_static -v
rtk python tools/test_rehab_mode_static.py
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4
rtk git diff --check
```

- [ ] **Step 5: Commit timing semantics**

```powershell
rtk git add applications/control/rehab_schedule.c applications/control/rehab_schedule.h applications/control/rehab_assist_strategy.c applications/control/rehab_assist_strategy.h applications/control/rehab_strategy.h applications/control/rehab_service.c applications/control/rehab_shell.c applications/control/control_layer_cfg.h tests/host/rehab_assist_v2_test.c tests/host/rehab_schedule_test.c tools/run_m33_gate01_host_tests.py
rtk git commit -m "fix(m33): run rehab control on measured time"
```

### Task 12: Full Software Gate And Release Candidate Manifest

**Files:**

- Create: `docs/GATE01_M33_RUNBOOK.md`
- Create: `docs/qa/m33-gate01/software-gate.txt`
- Output: `artifacts/firmware/m33-gate01-rc/manifest.json`

- [ ] **Step 1: Run the complete host/static suite from source**

```powershell
rtk python tools/run_m33_gate01_host_tests.py
rtk python -m unittest tools.test_m33_firmware_manifest tools.test_m33_observability_static tools.test_m33_gate01_static tools.test_m33_can_direct_recv_static tools.test_m33_scheduler_sram_linker_static tools.test_m33_smif_cache_static -v
rtk python tools/test_rehab_mode_static.py
rtk git diff --check
```

Expected: every command exits zero. Save exact output, compiler version, and test list; a prebuilt executable does not satisfy this step.

- [ ] **Step 2: Document exact board profile prerequisites**

The runbook must have blank, sign-off-required fields for board serial, assist joint, motor protocol, torque sign evidence, current cap source, physical cutoff, CAN termination/bitrate measurement, firmware manifest hash, operator, and date. A missing field means powered assist is prohibited.

- [ ] **Step 3: Commit the software evidence before creating an RC**

```powershell
rtk git add docs/GATE01_M33_RUNBOOK.md docs/qa/m33-gate01/software-gate.txt
rtk git commit -m "docs(m33): define gate01 board acceptance"
```

Expected: test output and runbook are now part of HEAD, so the subsequent firmware identity can match a clean commit.

- [ ] **Step 4: Clean-build the firmware in the approved toolchain**

Do not delete user files. Remove only SCons-owned outputs using the build system's clean target, then rebuild:

```powershell
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -c
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4
```

Expected: `rt-thread.elf`, `rtthread.map`, and `build/rtthread.hex` are regenerated. Review text/data/bss and `.cy_sharedmem` against the baseline; unexplained growth blocks release.

- [ ] **Step 5: Require a clean candidate or mark it diagnostic-only**

```powershell
rtk git status --short
rtk python tools/m33_firmware_manifest.py create --output artifacts/firmware/m33-gate01-rc --paired-m55-root F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED
rtk python tools/m33_firmware_manifest.py verify --manifest artifacts/firmware/m33-gate01-rc/manifest.json
```

Expected for a release candidate: both M33 and paired M55 worktrees are clean, `releasable=true`, all artifact hashes verify, and both embedded SHAs equal their manifest HEADs. If either worktree remains dirty, use `--allow-dirty` only for diagnostic hardware testing and do not label the pair RC.

### Task 13: Board Acceptance In Four Escalation Stages

**Files:**

- Update with raw evidence: `docs/qa/m33-gate01/stage-a-motor-off.txt`
- Update with raw evidence: `docs/qa/m33-gate01/stage-b-fault-injection.txt`
- Update with raw evidence: `docs/qa/m33-gate01/stage-c-single-joint.txt`
- Update with raw evidence: `docs/qa/m33-gate01/stage-d-soak.txt`
- Update only after each pass: `docs/GATE01_M33_RUNBOOK.md`

No stage may be skipped. A host/static pass cannot substitute for hardware timing, CAN capture, real current, stop latency, or direction evidence.

- [ ] **Stage A: Motor-power-off scheduler and RX ownership**

Flash the exact M33 `build/rtthread.hex` and paired M55 `rtthread.hex` named by the verified RC manifest. Before traffic, capture M33 `fw_info` and M55 `m55_fw_info` from its console/boot log; if the M55 console is detached, read the exported identity symbol with the debugger and save that output. Both full SHAs must match the paired manifest before testing.

The current build has M55 IPC and EMG auto-start disabled. Start the existing producers explicitly, then reset counters:

```text
cmd_m55_ipc_start
cmd_m55_emg_stream 1 20 1
ipcm_reset
rtm_reset
canm_reset 1000000
canm_default
```

Run for 30 minutes with full M33/M55/F103/NanoPi traffic. Collect `fw_info`, `rtm_show`, `ipcm_show`, `canm_show`, `canm_ids`, `control_debug`, `m55qa_status`, `list thread`, and `list memheap` at start/end, then stop the generated stream with `cmd_m55_emg_stream 0 20 1`.

For this configured run, the required active runtime slots are main health, `ctrl_can`, `rehab_svc`, `m55_ipc`, and `m55_emg`. A disabled optional slot is reported as disabled, not failed; an expected active slot with no advancing alive sequence fails the stage.

Pass criteria: startup safe-stop pending mask reaches zero, one RX owner remains, no HardFault occurs, all critical alive counters advance, no CAN FIFO loss/bus-off or IPC conservation violation occurs, every thread has at least 30% measured stack margin, and both `heap` and `hyperam` remain stable. If the pending mask cannot clear, the stage remains safe but fails readiness; do not enable motion.

After the pass, update and commit only the exact evidence:

```powershell
rtk git add docs/GATE01_M33_RUNBOOK.md docs/qa/m33-gate01/stage-a-motor-off.txt
rtk git commit -m "test(m33): record gate01 stage-a board evidence"
```

- [ ] **Stage B: Powered but motion-inhibited safety rejection**

Build and verify the committed no-motion fault-injection profile after the Stage A evidence commit:

```powershell
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -c
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4 M33_MOTION_PROFILE=m33_gate01_faultinj
rtk python tools/m33_firmware_manifest.py create --output artifacts/firmware/m33-gate01-faultinj --paired-m55-root F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED
rtk python tools/m33_firmware_manifest.py verify --manifest artifacts/firmware/m33-gate01-faultinj/manifest.json
```

With the profile hard-gated to zero output and motor power disabled, inject missing heartbeat, uncalibrated mask, stale feedback, nonzero `fault_summary`, invalid torque sign, multi-joint `0x38`, and use `rehab_faultinj invalid_source` plus `rehab_faultinj queue_full` for deterministic source/queue cases. Run `rehab_faultinj stopping_retry` to verify the compiled STOPPING logic against its fake backend; do not disconnect or bus-off a powered motor to manufacture this failure.

Pass criteria: every case sets its expected `failure_mask` bit even when safe-profile/cap-zero bits are also set; primary `detail` remains deterministic. No run-mode/enable/nonzero-IQ frame appears, the ninth normal enqueue fails without losing STOP, invalid source returns `-RT_EINVAL`, heartbeat recovery does not re-enter assist, and injected zero/STOP failures remain STOPPING with bounded retries and no re-arm.

```powershell
rtk git add docs/GATE01_M33_RUNBOOK.md docs/qa/m33-gate01/stage-b-fault-injection.txt
rtk git commit -m "test(m33): record gate01 stage-b safety evidence"
```

- [ ] **Stage C: Single-joint unloaded assist**

Only after a reviewed profile supplies one joint's torque sign and nonzero current cap, test that single joint with an external CAN analyzer and current measurement. Start at the approved minimum, not at the repository's strategy maximum.

Create `config/motion_profiles/m33_bench_pse84_eval_epc2_lab1.h`, link it to the signed direction/current evidence, and build with `M33_MOTION_PROFILE=m33_bench_pse84_eval_epc2_lab1`. The default remains `m33_safe`; an uncommitted or out-of-tree profile is diagnostic-only and cannot produce an RC manifest.

Before committing or flashing, validate the real header with the same profile contract used in Task 4. This is a disabled-output review only; motor power remains off:

```powershell
rtk python tools/run_m33_gate01_host_tests.py --profile m33_bench_pse84_eval_epc2_lab1
rtk python -m unittest tools.test_m33_gate01_static tools.test_m33_firmware_manifest -v
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4 M33_MOTION_PROFILE=m33_bench_pse84_eval_epc2_lab1
```

Expected pre-commit contract output: bench `1`, clinical `0`, logging-only `0`, multi-joint `0`, raw/legacy motion `0`, fault injection `0`, an approved positive finite cap, and exactly one assist motor4/5/6 sign equal to `+1.0f` or `-1.0f` while every other unvalidated sign is zero. The resolved profile digest must match the file under review. Any mismatch blocks commit and flashing.

After that pass, commit only the reviewed profile and its disabled-output sign/current evidence, then rebuild from the commit and verify a clean selected-profile manifest:

```powershell
rtk git add config/motion_profiles/m33_bench_pse84_eval_epc2_lab1.h docs/GATE01_M33_RUNBOOK.md docs/qa/m33-gate01/stage-c-single-joint.txt
rtk git commit -m "safety(m33): add validated lab1 assist profile"
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -c
rtk F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4 M33_MOTION_PROFILE=m33_bench_pse84_eval_epc2_lab1
rtk python tools/m33_firmware_manifest.py create --output artifacts/firmware/m33-gate01-lab1-assist --paired-m55-root F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED
rtk python tools/m33_firmware_manifest.py verify --manifest artifacts/firmware/m33-gate01-lab1-assist/manifest.json
```

Expected: `releasable=true`, selected profile name/hash match the committed header, raw/legacy motion Shell remains disabled, and only the authorized rehab current path can produce nonzero output.

Pass criteria for 10 minutes:

- exactly one run-mode and one enable per mode entry;
- periodic traffic contains setpoint only;
- disengaged state writes zero without disable chatter;
- torque/velocity direction is correct in both directions;
- effective current never exceeds the minimum of all caps;
- deadline miss, queue drop, FIFO lost/full, bus-off, and unexpected re-arm are zero;
- heartbeat expiry starts zero+stop no later than one control period after TTL; any `tx_inflight_at_stop` is explicitly counted and bounded to the send already inside the driver;
- with successful TX, explicit STOP/stale feedback/motor fault create one logical stop and no stop chatter;

After the 10-minute pass, append the final trace and commit the exact runbook/evidence files:

```powershell
rtk git add docs/GATE01_M33_RUNBOOK.md docs/qa/m33-gate01/stage-c-single-joint.txt
rtk git commit -m "test(m33): record gate01 single-joint assist evidence"
```

- [ ] **Stage D: Repetition and soak**

Run 1,000 ASSIST/PASSIVE transitions and then a 24-hour mixed traffic soak. Do not wear the mechanism during this gate.

Pass criteria: no HardFault/reset, no kernel object duplication, no monotonic heap loss, no stack margin below 30%, no missed safety stop, no IPC count imbalance, no CAN RX loss, and zero control deadline misses. Any failure retains its raw logs and blocks the next gate.

```powershell
rtk git add docs/GATE01_M33_RUNBOOK.md docs/qa/m33-gate01/stage-d-soak.txt
rtk git commit -m "test(m33): record gate01 soak evidence"
```

---

## Final Acceptance Matrix

| Area | Required evidence | Gate 0-1 pass condition |
|---|---|---|
| Build identity | `fw_info` + verified manifest | Board SHA/config/artifact hash agree; clean RC only |
| Scheduling | `rtm_show`, `list thread` | main blocked at p25, CAN p18 and rehab p21 alive, zero deadline misses |
| CAN RX | source/static guard + analyzer + `canm_*` | exactly one RX owner, no FIFO loss/drain-limit/bus-off |
| IPC observation | `ipcm_show` | queue/error/seq counters explain every local failure; ABI unchanged |
| M55 result forwarding | model bridge metrics | `ai_rx = can_forward_ok + can_forward_fail + in_flight`; quiescent `in_flight=0` |
| Command architecture | broker host tests | CAN/Shell enqueue; one worker mutates mode; STOP cannot drop |
| Heartbeat | lease host + board fault injection | one logical expiry transition; recovery requires new mode command |
| Prearm | table-driven host + powered inhibited test | every missing condition rejects before motor output |
| Motor lifecycle | fake ops + CAN analyzer | prepare/enable once, setpoint-only loop, STOPPING retries failures without re-arm |
| Assist timing | algorithm host + runtime metrics | actual `dt`, rate slew, correct direction/cap, no deadline miss |
| Memory | map, `list thread`, `list memheap` | shared ABI unchanged, >=30% stack margin, no heap drift |

## Explicit Stop Conditions

Stop execution and investigate before continuing when any of these occurs:

- phase A loses CAN RX after adding the real delay;
- phase B shows two FIFO consumers or any direct diagnostic FIFO read;
- scheduler fix causes an unexpected motor command in the safe profile;
- firmware identity is `unknown` or manifest artifact differs from flashed image;
- `fault_summary != 0` coexists with nonzero current output;
- heartbeat expiry, explicit STOP, or stale feedback does not reach zero+stop within one period;
- direction cannot be proven with motor output disabled and then unloaded;
- `.cy_sharedmem` changes during Gate 0 metrics work;
- any test requires setting safety confirmation macros to fabricated values;
- any board run produces HardFault, reset, stack margin below 30%, CAN FIFO loss, or control deadline miss.

## Next Plan After This Gate

Only after all Gate 0-1 evidence passes should the next implementation plan address full `can_service` TX ownership, mailbox arbitration and bus-off recovery, CAN boot handshake/filter/QoS, IPC V2 epoch/CRC/rings, NanoPi reconnect/outbox, cloud idempotency/correlation ID, and finally BLE pairing. Those changes must not be pulled into this plan as opportunistic refactors.
