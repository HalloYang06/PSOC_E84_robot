# PSOC E84 Robot Monorepo Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 M33、M55、C8T6、正式 ROS2、康复 App/平台和 VLA 的有效代码与主线历史迁入 `HalloYang06/PSOC_E84_robot` 的单一 `main`，并交付可导航、可验证的新 README。

**Architecture:** 每个来源 ref 以审计确认的原始 SHA 作为 `ours` merge 的第二父提交，再用 `git read-tree --prefix` 将完整 tree 或选定子目录放入目标前缀；原始提交对象和 SHA 不变，当前 tree 按 monorepo 目录组织。固件保持三个独立构建工程；ROS 只导入正式 workspace；`ai-` 只导入康复 App、平台及其依赖闭包，并从集成提交的当前 tree 删除农场游戏等排除内容。迁移全过程只使用本地 worktree 分支，最终审计通过后仅推送 `main`。

**Tech Stack:** Git、PowerShell、Python 3.12/pytest、RT-Thread/SCons、ROS 2 Jazzy/colcon、Node.js/Next.js、FastAPI、Capacitor/Gradle、GitHub Actions。

---

## 文件结构锁定

本计划创建或修改的仓库级文件：

- `.gitignore`：统一忽略固件、ROS、Node、Python、Android 和本地数据库输出。
- `.gitattributes`：固定文本换行策略，并把固件二进制资源标成 binary。
- `README.md`：完整项目入口。
- `docs/migration/source-map.md`：人类可读来源与迁移结果。
- `docs/migration/source-map.json`：机器可读来源、准确的原始提交 SHA 和集成 merge commit SHA。
- `docs/architecture/system-overview.md`：产品分层与数据流。
- `docs/protocols/can-protocol.md`：CAN 协议入口。
- `docs/protocols/m33-m55-ipc.md`：双核 IPC 入口。
- `docs/protocols/app-api.md`：App/Web/API/NanoPi 接口入口。
- `docs/protocols/safety-boundary.md`：运动权限与故障边界。
- `tools/test/test_repository_layout.py`：目录、生成物和正式入口守卫。
- `tools/test/test_history_provenance.py`：迁移来源与 Git 历史守卫。
- `tools/test/verify_all.ps1`：全仓验证入口。
- `.github/workflows/repository-structure.yml`：无需硬件的持续检查。

导入目录：

- `firmware/m33/`、`firmware/m55/`、`firmware/c8t6/`
- `ros/rehab_arm_ws/`
- `apps/mobile/`
- `platform/web/`、`platform/api/`、`platform/runner/`、`platform/shared/`、`platform/deploy/`
- `ai/vla/`

## Task 1: 建立迁移防护

**Files:**
- Create: `.gitignore`
- Create: `.gitattributes`
- Create: `tools/test/test_repository_layout.py`

- [ ] **Step 1: 固定当前设计提交和空远端状态**

Run:

```powershell
rtk git status --short --branch
rtk git log -1 --oneline
rtk git ls-remote --heads origin
```

Expected: 当前位于仅供本地迁移执行的 `codex/monorepo-migration` worktree 分支，只有计划/设计文档改动；目标远端仍无分支，且整个迁移期间不创建或推送远端 history/migration 分支。

- [ ] **Step 2: 验证 Git 具备精确历史接入所需命令**

Run:

```powershell
rtk git version --build-options
```

Expected: Git 版本和构建信息正常输出；迁移只依赖 Git 内置的 merge、read-tree、cat-file 和 merge-base，不安装额外历史工具。

- [ ] **Step 3: 先写仓库卫生测试**

Create `tools/test/test_repository_layout.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_PARTS = {
    ".gradle",
    ".pytest_cache",
    "__pycache__",
    "build",
    "install",
    "log",
    "node_modules",
}
FORBIDDEN_SUFFIXES = {".apk", ".db", ".pyc"}


def tracked_paths() -> list[Path]:
    import subprocess

    output = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=ROOT
    ).decode("utf-8", errors="surrogateescape")
    return [Path(item) for item in output.split("\0") if item]


def test_no_generated_or_runtime_artifacts_are_tracked() -> None:
    bad = [
        str(path)
        for path in tracked_paths()
        if FORBIDDEN_PARTS.intersection(path.parts)
        or path.suffix.lower() in FORBIDDEN_SUFFIXES
    ]
    assert bad == []


def test_design_document_exists() -> None:
    assert (
        ROOT
        / "docs/superpowers/specs/2026-07-13-monorepo-migration-design.md"
    ).is_file()
```

- [ ] **Step 4: 运行测试并记录首次失败**

Run:

```powershell
rtk python -m pytest tools/test/test_repository_layout.py -v
```

Expected: 当前设计文档测试通过；若已有生成物被跟踪，生成物测试失败并列出路径。

- [ ] **Step 5: 添加统一忽略规则**

Create `.gitignore`:

```gitignore
# Python
__pycache__/
*.py[cod]
.pytest_cache/
.venv/

# Node / web
node_modules/
.next/
coverage/

# Android / Gradle
.gradle/
**/build/
*.apk
local.properties

# ROS 2
ros/**/build/
ros/**/install/
ros/**/log/

# Firmware outputs
*.elf
*.hex
*.bin
*.map
.sconsign.dblite

# Runtime data and secrets
*.db
*.sqlite
*.sqlite3
.env
!.env.example

# Local migration scratch
.migration/
```

Create `.gitattributes`:

```gitattributes
* text=auto
*.sh text eol=lf
*.py text eol=lf
*.c text eol=lf
*.h text eol=lf
*.ps1 text eol=crlf
*.bat text eol=crlf
*.png binary
*.jpg binary
*.jpeg binary
*.zip binary
*.a binary
*.lib binary
*.jar binary
```

- [ ] **Step 6: 运行测试并提交防护文件**

Run:

```powershell
rtk python -m pytest tools/test/test_repository_layout.py -v
rtk git add .gitignore .gitattributes tools/test/test_repository_layout.py docs/superpowers
rtk git commit -m "chore: add monorepo migration guards"
```

Expected: `2 passed`，提交成功。

## Task 2: 以原始 SHA 历史迁入 M33

**Files:**
- Import: `firmware/m33/**`
- Modify: `docs/migration/source-map.md`
- Modify: `docs/migration/source-map.json`

- [ ] **Step 1: 获取 M33 ref 并固定准确来源提交**

Run:

```powershell
rtk git fetch https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator.git refs/heads/M33
rtk git rev-parse FETCH_HEAD
```

Expected: `FETCH_HEAD` 为执行时确认的正式 M33 tip；若不再是完整基线 `24bae363c50a221dbbaf61c041dfa501a9e539b4`，先审计新增提交并更新 source map，不能静默继续。

- [ ] **Step 2: 以原始 M33 tip 作为第二父提交并写入目标前缀**

Run:

```powershell
rtk powershell -NoProfile -Command 'function Invoke-Git { & git @args; if($LASTEXITCODE){throw "git $args failed"} }; $url="https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator.git"; $ref="refs/heads/M33"; $baseline="24bae363c50a221dbbaf61c041dfa501a9e539b4"; Invoke-Git fetch $url $ref; $sourceSha=(git rev-parse FETCH_HEAD).Trim(); if($sourceSha -notmatch "^[0-9a-f]{40}$"){throw "Invalid source SHA: $sourceSha"}; if($sourceSha -ne $baseline -and $env:M33_SOURCE_SHA -ne $sourceSha){throw "Tip advanced to $sourceSha; audit it, set M33_SOURCE_SHA to that exact SHA, and rerun"}; Invoke-Git fetch $url $sourceSha; if((git rev-parse FETCH_HEAD).Trim() -ne $sourceSha){throw "Exact SHA fetch mismatch"}; try { Invoke-Git merge -s ours --allow-unrelated-histories --no-commit $sourceSha; Invoke-Git read-tree --prefix=firmware/m33/ -u $sourceSha; Invoke-Git commit -m "merge: import M33 firmware history"; Invoke-Git diff --exit-code "${sourceSha}^{tree}" "HEAD:firmware/m33"; Invoke-Git cat-file -e "${sourceSha}^{commit}"; Invoke-Git merge-base --is-ancestor $sourceSha HEAD; $second=(git rev-parse HEAD^2).Trim(); if($second -ne $sourceSha){throw "Second parent $second != source $sourceSha"}; Write-Output "source_commit=$sourceSha"; Write-Output "integration_commit=$((git rev-parse HEAD).Trim())" } catch { git merge --abort 2>$null; throw }'
```

Expected: `firmware/m33/SConstruct` 和 `firmware/m33/applications/main.c` 存在；集成提交的第二父提交是准确的原始 M33 tip。

Expected: 同一不可变 `$sourceSha` 完成精确抓取、merge、read-tree、tree 对比、对象检查、祖先检查和第二父提交断言；输出实际 `source_commit` 与 `integration_commit` 供 source map 使用。普通路径日志从集成提交开始是预期行为，旧路径历史通过该原始 SHA 或第二父历史导航。

## Task 3: 以原始 SHA 历史迁入 M55

**Files:**
- Import: `firmware/m55/**`

- [ ] **Step 1: 获取并核对 M55 来源 tip**

Run:

```powershell
rtk git fetch https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator.git refs/heads/M55
rtk git rev-parse FETCH_HEAD
```

Expected: `FETCH_HEAD` 为完整基线 `7298c28e81b43fdb5b37e84408cfc62895eaea85`，或为经审计并更新 source map 后的新正式 tip；WEN 临时延迟分支不自动替代它。

- [ ] **Step 2: 以原始 M55 tip 作为第二父提交并写入目标前缀**

Run:

```powershell
rtk powershell -NoProfile -Command 'function Invoke-Git { & git @args; if($LASTEXITCODE){throw "git $args failed"} }; $url="https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator.git"; $ref="refs/heads/M55"; $baseline="7298c28e81b43fdb5b37e84408cfc62895eaea85"; Invoke-Git fetch $url $ref; $sourceSha=(git rev-parse FETCH_HEAD).Trim(); if($sourceSha -notmatch "^[0-9a-f]{40}$"){throw "Invalid source SHA: $sourceSha"}; if($sourceSha -ne $baseline -and $env:M55_SOURCE_SHA -ne $sourceSha){throw "Tip advanced to $sourceSha; audit it, set M55_SOURCE_SHA to that exact SHA, and rerun"}; Invoke-Git fetch $url $sourceSha; if((git rev-parse FETCH_HEAD).Trim() -ne $sourceSha){throw "Exact SHA fetch mismatch"}; try { Invoke-Git merge -s ours --allow-unrelated-histories --no-commit $sourceSha; Invoke-Git read-tree --prefix=firmware/m55/ -u $sourceSha; Invoke-Git commit -m "merge: import M55 firmware history"; Invoke-Git diff --exit-code "${sourceSha}^{tree}" "HEAD:firmware/m55"; Invoke-Git cat-file -e "${sourceSha}^{commit}"; Invoke-Git merge-base --is-ancestor $sourceSha HEAD; $second=(git rev-parse HEAD^2).Trim(); if($second -ne $sourceSha){throw "Second parent $second != source $sourceSha"}; Write-Output "source_commit=$sourceSha"; Write-Output "integration_commit=$((git rev-parse HEAD).Trim())" } catch { git merge --abort 2>$null; throw }'
```

Expected: `firmware/m55/SConstruct`、M55 applications 存在，集成提交的第二父提交是准确的原始 M55 tip。

Expected: 同一不可变 `$sourceSha` 完成导入和全部历史断言；tree 完全一致，第二父提交精确等于实际来源 SHA，并输出 source map 所需的两个完整 SHA。

## Task 4: 以原始 SHA 历史迁入 C8T6

**Files:**
- Import: `firmware/c8t6/**`

- [ ] **Step 1: 获取 C8T6 ref 并确认实时 tip**

Run:

```powershell
rtk git fetch https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator.git refs/heads/C8T6
rtk git rev-parse FETCH_HEAD
```

Expected: `FETCH_HEAD` 为完整基线 `28b79a09dd4813fb31cc776f402183a75ed0e153`，或为经审计并更新 source map 后的新正式 tip。

- [ ] **Step 2: 以原始 C8T6 tip 作为第二父提交并写入目标前缀**

Run:

```powershell
rtk powershell -NoProfile -Command 'function Invoke-Git { & git @args; if($LASTEXITCODE){throw "git $args failed"} }; $url="https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator.git"; $ref="refs/heads/C8T6"; $baseline="28b79a09dd4813fb31cc776f402183a75ed0e153"; Invoke-Git fetch $url $ref; $sourceSha=(git rev-parse FETCH_HEAD).Trim(); if($sourceSha -notmatch "^[0-9a-f]{40}$"){throw "Invalid source SHA: $sourceSha"}; if($sourceSha -ne $baseline -and $env:C8T6_SOURCE_SHA -ne $sourceSha){throw "Tip advanced to $sourceSha; audit it, set C8T6_SOURCE_SHA to that exact SHA, and rerun"}; Invoke-Git fetch $url $sourceSha; if((git rev-parse FETCH_HEAD).Trim() -ne $sourceSha){throw "Exact SHA fetch mismatch"}; try { Invoke-Git merge -s ours --allow-unrelated-histories --no-commit $sourceSha; Invoke-Git read-tree --prefix=firmware/c8t6/ -u $sourceSha; Invoke-Git commit -m "merge: import C8T6 sensor firmware history"; Invoke-Git diff --exit-code "${sourceSha}^{tree}" "HEAD:firmware/c8t6"; Invoke-Git cat-file -e "${sourceSha}^{commit}"; Invoke-Git merge-base --is-ancestor $sourceSha HEAD; $second=(git rev-parse HEAD^2).Trim(); if($second -ne $sourceSha){throw "Second parent $second != source $sourceSha"}; Write-Output "source_commit=$sourceSha"; Write-Output "integration_commit=$((git rev-parse HEAD).Trim())" } catch { git merge --abort 2>$null; throw }'
```

Expected: C8T6 工程进入 `firmware/c8t6/`，集成提交的第二父提交是准确的原始 C8T6 tip。

Expected: 同一不可变 `$sourceSha` 完成导入和全部历史断言；tree 对比通过，第二父提交精确等于实际来源 SHA，并输出 source map 所需的两个完整 SHA。

## Task 5: 带历史迁入正式 ROS2 workspace

**Files:**
- Import: `ros/rehab_arm_ws/**`
- Create: `ros/rehab_arm_ws/src/rehab_arm_bringup/test/test_mainline_boundaries.py`
- Create: `tools/bench-debug/legacy-5dof/README.md`

- [ ] **Step 1: 获取正式 ROS feature ref 并确认实时 tip**

Run:

```powershell
rtk git fetch https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator.git refs/heads/feature/rehab-arm-ros2-architecture
rtk git rev-parse FETCH_HEAD
```

Expected: `FETCH_HEAD` 为完整基线 `69450f7165e608f99fc4b574beffa5ac50d2331f`，或为经审计并更新 source map 后的新正式 tip。

- [ ] **Step 2: 以原始 feature tip 为第二父提交，只写入正式 workspace**

Run:

```powershell
rtk powershell -NoProfile -Command 'function Invoke-Git { & git @args; if($LASTEXITCODE){throw "git $args failed"} }; $url="https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator.git"; $ref="refs/heads/feature/rehab-arm-ros2-architecture"; $baseline="69450f7165e608f99fc4b574beffa5ac50d2331f"; Invoke-Git fetch $url $ref; $sourceSha=(git rev-parse FETCH_HEAD).Trim(); if($sourceSha -notmatch "^[0-9a-f]{40}$"){throw "Invalid source SHA: $sourceSha"}; if($sourceSha -ne $baseline -and $env:ROS_SOURCE_SHA -ne $sourceSha){throw "Tip advanced to $sourceSha; audit it, set ROS_SOURCE_SHA to that exact SHA, and rerun"}; Invoke-Git fetch $url $sourceSha; if((git rev-parse FETCH_HEAD).Trim() -ne $sourceSha){throw "Exact SHA fetch mismatch"}; try { Invoke-Git merge -s ours --allow-unrelated-histories --no-commit $sourceSha; Invoke-Git read-tree --prefix=ros/rehab_arm_ws/ -u "${sourceSha}:rehab_arm_ros2_ws"; Invoke-Git commit -m "merge: import formal ROS2 workspace history"; Invoke-Git diff --exit-code "${sourceSha}:rehab_arm_ros2_ws" "HEAD:ros/rehab_arm_ws"; Invoke-Git cat-file -e "${sourceSha}^{commit}"; Invoke-Git merge-base --is-ancestor $sourceSha HEAD; $second=(git rev-parse HEAD^2).Trim(); if($second -ne $sourceSha){throw "Second parent $second != source $sourceSha"}; Write-Output "source_commit=$sourceSha"; Write-Output "integration_commit=$((git rev-parse HEAD).Trim())" } catch { git merge --abort 2>$null; throw }'
```

Expected: `ros/rehab_arm_ws/src/rehab_arm_psoc_bridge`、6DOF description 和 MuJoCo 包存在；旧根级 HTTP bridge、`ROS_VLA_WebSocket` 和 NanoPi 早期 workspace 不在当前 tree。原始 feature tip 是集成提交的第二父提交，且其全部历史 SHA 保持不变。

Expected: 同一不可变 `$sourceSha` 完成正式 workspace 导入和全部历史断言；子树完全一致，第二父提交精确等于实际来源 SHA，并输出 source map 所需的两个完整 SHA。

- [ ] **Step 4: 先写正式入口边界测试**

Create `ros/rehab_arm_ws/src/rehab_arm_bringup/test/test_mainline_boundaries.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
FORMAL_LAUNCH_ROOT = ROOT / "ros/rehab_arm_ws/src/rehab_arm_bringup/launch"


def test_formal_launches_do_not_enable_legacy_motion_publishers() -> None:
    offenders: list[str] = []
    for path in FORMAL_LAUNCH_ROOT.glob("*.launch.py"):
        text = path.read_text(encoding="utf-8")
        if path.name == "sim_data_collection.launch.py":
            continue
        if "demo_trajectory_node" in text or "vla_task_planner_node" in text:
            offenders.append(path.name)
    assert offenders == []


def test_sim_data_collection_keeps_demo_disabled_by_default() -> None:
    text = (FORMAL_LAUNCH_ROOT / "sim_data_collection.launch.py").read_text(
        encoding="utf-8"
    )
    assert "DeclareLaunchArgument('enable_demo_trajectory', default_value='false')" in text
```

- [ ] **Step 5: 运行边界测试并补充隔离说明**

Run:

```powershell
rtk python -m pytest ros/rehab_arm_ws/src/rehab_arm_bringup/test/test_mainline_boundaries.py -v
```

Expected: 两项测试通过。若正式 launch 引用了 demo，先移除该引用再继续。

Create `tools/bench-debug/legacy-5dof/README.md` with these exact rules:

```markdown
# Legacy 5DOF ROS demos

The historical `demo_trajectory_node` and `vla_task_planner_node` are retained
inside the ROS package so their tests and history remain traceable. They are
offline/demo publishers only. They must not be referenced by a real-device
launch file or used as evidence of 6DOF hardware readiness.
```

- [ ] **Step 6: 提交 ROS 边界守卫**

Run:

```powershell
rtk git add ros/rehab_arm_ws/src/rehab_arm_bringup/test/test_mainline_boundaries.py tools/bench-debug/legacy-5dof/README.md
rtk git commit -m "test: guard formal ROS2 motion boundaries"
```

Expected: 提交成功。

## Task 6: 带历史迁入康复 App 与平台

**Files:**
- Import: `apps/mobile/**`
- Import: `platform/web/**`
- Import: `platform/api/**`
- Import: `platform/runner/**`
- Import: `platform/shared/**`
- Import: `platform/deploy/**`
- Modify: `apps/mobile/scripts/sync-web-assets.mjs`
- Modify: `platform/package.json`

- [ ] **Step 1: 获取 `ai-` 康复分支并固定准确来源 SHA**

Run:

```powershell
rtk git fetch https://github.com/wenjunyong666/ai-.git refs/heads/app/rehab-arm-mobile-stitch
rtk git rev-parse FETCH_HEAD
```

Expected: `FETCH_HEAD` 为完整审计基线 `f6c2c026ce6acda074608aa3e3ada880d62c62d3`；若 ref 已前进，先阅读新增提交并更新 source map，不能静默继续。

- [ ] **Step 2: 以原始分支 tip 为第二父提交并写入选定子树**

Run:

```powershell
rtk powershell -NoProfile -Command 'function Invoke-Git { & git @args; if($LASTEXITCODE){throw "git $args failed"} }; function Assert-ImportedTree($sourceSpec,$targetPrefix) { $sourceTree=(git rev-parse $sourceSpec).Trim(); $targetTree=(git write-tree --prefix=$targetPrefix).Trim(); Invoke-Git diff --exit-code $sourceTree $targetTree }; $url="https://github.com/wenjunyong666/ai-.git"; $ref="refs/heads/app/rehab-arm-mobile-stitch"; $baseline="f6c2c026ce6acda074608aa3e3ada880d62c62d3"; Invoke-Git fetch $url $ref; $sourceSha=(git rev-parse FETCH_HEAD).Trim(); if($sourceSha -notmatch "^[0-9a-f]{40}$"){throw "Invalid source SHA: $sourceSha"}; if($sourceSha -ne $baseline -and $env:PLATFORM_SOURCE_SHA -ne $sourceSha){throw "Tip advanced to $sourceSha; audit it, set PLATFORM_SOURCE_SHA to that exact SHA, and rerun"}; Invoke-Git fetch $url $sourceSha; if((git rev-parse FETCH_HEAD).Trim() -ne $sourceSha){throw "Exact SHA fetch mismatch"}; try { Invoke-Git merge -s ours --allow-unrelated-histories --no-commit $sourceSha; Invoke-Git read-tree --prefix=apps/mobile/ -u "${sourceSha}:apps/mobile/rehab-arm-android"; Invoke-Git read-tree --prefix=platform/web/ -u "${sourceSha}:apps/web"; Invoke-Git read-tree --prefix=platform/api/ -u "${sourceSha}:apps/api"; Invoke-Git read-tree --prefix=platform/runner/ -u "${sourceSha}:apps/runner"; Invoke-Git read-tree --prefix=platform/shared/ -u "${sourceSha}:packages/shared"; Invoke-Git read-tree --prefix=platform/deploy/ -u "${sourceSha}:infra"; Assert-ImportedTree "${sourceSha}:apps/mobile/rehab-arm-android" "apps/mobile/"; Assert-ImportedTree "${sourceSha}:apps/web" "platform/web/"; Assert-ImportedTree "${sourceSha}:apps/api" "platform/api/"; Assert-ImportedTree "${sourceSha}:apps/runner" "platform/runner/"; Assert-ImportedTree "${sourceSha}:packages/shared" "platform/shared/"; Assert-ImportedTree "${sourceSha}:infra" "platform/deploy/"; Invoke-Git checkout $sourceSha -- package.json package-lock.json; Invoke-Git mv package.json platform/package.json; Invoke-Git mv package-lock.json platform/package-lock.json; Invoke-Git rm -r -f --ignore-unmatch -- platform/web/public/harvest-moon-phaser3-game ":(literal)platform/web/app/projects/[id]/2d-upgrade" platform/web/lib/game ":(glob)platform/web/public/downloads/rehab-arm/*.apk"; Invoke-Git commit -m "merge: import rehabilitation app and platform history"; Invoke-Git cat-file -e "${sourceSha}^{commit}"; Invoke-Git merge-base --is-ancestor $sourceSha HEAD; $second=(git rev-parse HEAD^2).Trim(); if($second -ne $sourceSha){throw "Second parent $second != source $sourceSha"}; Write-Output "source_commit=$sourceSha"; Write-Output "integration_commit=$((git rev-parse HEAD).Trim())" } catch { git merge --abort 2>$null; throw }'
```

Expected: App、Web、API、Runner、shared 和 deploy 位于目标目录；来源根 `package.json` 和 `package-lock.json` 经 index-safe `git checkout`/`git mv` 进入 `platform/`；集成提交的当前 tree 明确排除 APK、Harvest Moon 静态游戏、`2d-upgrade` 游戏页和 `lib/game`。未选中的 `docs/screenshots` 等来源路径不进入当前 tree。

- [ ] **Step 3: 校验 App/平台排除项**

Run:

```powershell
rtk git ls-files "*.apk" "platform/web/public/harvest-moon-phaser3-game/**" ":(literal)platform/web/app/projects/[id]/2d-upgrade" "platform/web/lib/game/**"
```

Expected: Step 2 已用同一不可变 `$sourceSha` 断言原始 `ai-` SHA 存在、是 `HEAD` 的祖先且精确等于 `HEAD^2`，并输出 source map 所需的两个 SHA；本步骤命令无输出。

- [ ] **Step 4: 先验证旧同步路径会失败**

Run:

```powershell
rtk npm --prefix apps/mobile run sync:web
```

Expected: FAIL，错误指出旧 `apps/web/public/rehab-arm-mobile` 不存在。

- [ ] **Step 5: 修正移动端资源源路径**

Modify `apps/mobile/scripts/sync-web-assets.mjs`:

```javascript
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

try {
  const here = path.dirname(fileURLToPath(import.meta.url));
  const mobileRoot = path.resolve(here, "..");
  const repoRoot = path.resolve(mobileRoot, "..", "..");
  const source = path.join(repoRoot, "platform", "web", "public", "rehab-arm-mobile");
  const target = path.join(mobileRoot, "www");

  if (!fs.existsSync(source)) {
    throw new Error(`Missing PWA source directory: ${source}`);
  }

  fs.rmSync(target, { recursive: true, force: true });
  fs.mkdirSync(target, { recursive: true });
  copyTree(source, target);

  const indexPath = path.join(target, "index.html");
  let indexHtml = fs.readFileSync(indexPath, "utf8");
  indexHtml = indexHtml.replace(
    "</head>",
    '    <meta name="capacitor-app-shell" content="android" />\n  </head>'
  );
  fs.writeFileSync(indexPath, indexHtml, "utf8");
  console.log(`Synced ${source} -> ${target}`);
} catch (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
}

function copyTree(sourceDir, targetDir) {
  for (const entry of fs.readdirSync(sourceDir, { withFileTypes: true })) {
    const sourcePath = path.join(sourceDir, entry.name);
    const targetPath = path.join(targetDir, entry.name);
    if (entry.isDirectory()) {
      fs.mkdirSync(targetPath, { recursive: true });
      copyTree(sourcePath, targetPath);
      continue;
    }
    if (entry.isFile()) {
      fs.copyFileSync(sourcePath, targetPath);
    }
  }
}
```

- [ ] **Step 6: 修正平台 workspace 路径**

Modify `platform/package.json` so its workspace section is:

```json
{
  "name": "rehab-platform",
  "private": true,
  "version": "0.1.0",
  "workspaces": ["web", "shared"],
  "scripts": {
    "dev:web": "npm --workspace web run dev",
    "build:web": "npm --workspace web run build",
    "lint:web": "npm --workspace web run lint"
  },
  "dependencies": {
    "graceful-fs": "^4.2.11"
  },
  "devDependencies": {
    "playwright": "^1.59.1"
  }
}
```

- [ ] **Step 7: 重新生成与新 workspace 路径一致的 lockfile**

Run:

```powershell
rtk npm --prefix platform install --package-lock-only
rtk npm --prefix platform ci
```

Expected: lockfile workspace 路径为 `web` 和 `shared`，`npm ci` 退出码为 0。

- [ ] **Step 8: 验证平台、API 与移动资源同步**

Run:

```powershell
rtk npm --prefix platform run build:web
rtk python -m pip install -r platform/api/requirements.txt
rtk python -m pytest platform/api/tests/test_rehab_arm_app_backend.py platform/api/tests/test_rehab_arm_app_live_emg.py platform/api/tests/test_rehab_arm_sync.py platform/api/tests/test_rehab_arm_vla_closed_loop_status.py -v
rtk npm --prefix apps/mobile ci
rtk npm --prefix apps/mobile run sync:web
```

Expected: Web production build、四组康复 API 测试和 PWA 同步全部通过；`apps/mobile/www` 与 `platform/web/public/rehab-arm-mobile` 文件内容一致，仅 Android shell 注入标记不同。

- [ ] **Step 9: 提交路径适配和无关内容清理**

Run:

```powershell
rtk git add apps/mobile platform
rtk git commit -m "refactor: align rehabilitation platform paths"
```

Expected: 提交不包含 `node_modules`、`.next`、APK 或数据库。

## Task 7: 带历史迁入 VLA 原型并明确权限

**Files:**
- Import: `ai/vla/**`
- Create: `ai/vla/README.md`

- [ ] **Step 1: 获取原始 `ai` ref 并只写入 VLA 子树**

Run:

```powershell
rtk powershell -NoProfile -Command 'function Invoke-Git { & git @args; if($LASTEXITCODE){throw "git $args failed"} }; $url="https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator.git"; $ref="refs/heads/ai"; $baseline="517df8f37105f659f2fe3561b46540ced830c731"; Invoke-Git fetch $url $ref; $sourceSha=(git rev-parse FETCH_HEAD).Trim(); if($sourceSha -notmatch "^[0-9a-f]{40}$"){throw "Invalid source SHA: $sourceSha"}; if($sourceSha -ne $baseline -and $env:VLA_SOURCE_SHA -ne $sourceSha){throw "Tip advanced to $sourceSha; audit it, set VLA_SOURCE_SHA to that exact SHA, and rerun"}; Invoke-Git fetch $url $sourceSha; if((git rev-parse FETCH_HEAD).Trim() -ne $sourceSha){throw "Exact SHA fetch mismatch"}; try { Invoke-Git merge -s ours --allow-unrelated-histories --no-commit $sourceSha; Invoke-Git read-tree --prefix=ai/vla/ -u "${sourceSha}:vla_system"; Invoke-Git commit -m "merge: import VLA prototype history"; Invoke-Git diff --exit-code "${sourceSha}:vla_system" "HEAD:ai/vla"; Invoke-Git cat-file -e "${sourceSha}^{commit}"; Invoke-Git merge-base --is-ancestor $sourceSha HEAD; $second=(git rev-parse HEAD^2).Trim(); if($second -ne $sourceSha){throw "Second parent $second != source $sourceSha"}; Write-Output "source_commit=$sourceSha"; Write-Output "integration_commit=$((git rev-parse HEAD).Trim())" } catch { git merge --abort 2>$null; throw }'
```

Expected: 实时 tip 为审计 SHA `517df8f37105f659f2fe3561b46540ced830c731`，或为经审计并更新 source map 后的新正式 tip；VLA schema、验证器和测试在 `ai/vla/`，没有电机/CAN 直控实现，原始 `ai` tip 是集成提交的第二父提交。

Expected: 同一不可变 `$sourceSha` 完成 VLA 子树导入和全部历史断言；子树完全一致，第二父提交精确等于实际来源 SHA，并输出 source map 所需的两个完整 SHA。

- [ ] **Step 3: 写权限说明并运行原有测试**

Create `ai/vla/README.md`:

```markdown
# VLA high-level task layer

This directory contains task parsing, grounding, schemas, validation, and
offline evaluation. Its output is a high-level request or a dry-run candidate.
It does not own CAN, motor current, torque, raw setpoints, emergency-stop
release, or M33 safety override. ROS adapters remain in `ros/rehab_arm_ws`.
```

Run:

```powershell
rtk python -m pytest ai/vla/tests -v
rtk rg -n -i "socketcan|cansend|motor current|torque command|m33 override" ai/vla
```

Expected: 测试通过；搜索结果只能出现在禁止规则、测试或文档中，不能出现实际直控调用。

- [ ] **Step 4: 提交 VLA 边界说明**

Run:

```powershell
rtk git add ai/vla/README.md
rtk git commit -m "docs: define VLA high-level control boundary"
```

Expected: 提交成功。

## Task 8: 建立来源映射与历史回归测试

**Files:**
- Create: `docs/migration/source-map.json`
- Create: `docs/migration/source-map.md`
- Create: `tools/test/test_history_provenance.py`

- [ ] **Step 1: 写机器可读来源映射**

Create `docs/migration/source-map.json` with the actual refreshed full source hashes and the exact full integration commit hashes recorded in Tasks 2–7. Every component object must contain both `source_commit` and `integration_commit`; copy the real 40-character `git rev-parse HEAD` output for the latter, never an abbreviated hash or sample value. The fixed fields are:

```json
{
  "schema_version": 1,
  "target_repository": "https://github.com/HalloYang06/PSOC_E84_robot",
  "target_branch": "main",
  "components": [
    {"name": "m33", "source_repository": "https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator", "source_ref": "M33", "source_commit": "24bae363c50a221dbbaf61c041dfa501a9e539b4", "target_path": "firmware/m33"},
    {"name": "m55", "source_repository": "https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator", "source_ref": "M55", "source_commit": "7298c28e81b43fdb5b37e84408cfc62895eaea85", "target_path": "firmware/m55"},
    {"name": "c8t6", "source_repository": "https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator", "source_ref": "C8T6", "source_commit": "28b79a09dd4813fb31cc776f402183a75ed0e153", "target_path": "firmware/c8t6"},
    {"name": "ros", "source_repository": "https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator", "source_ref": "feature/rehab-arm-ros2-architecture", "source_commit": "69450f7165e608f99fc4b574beffa5ac50d2331f", "target_path": "ros/rehab_arm_ws"},
    {"name": "rehab-platform", "source_repository": "https://github.com/wenjunyong666/ai-", "source_ref": "app/rehab-arm-mobile-stitch", "source_commit": "f6c2c026ce6acda074608aa3e3ada880d62c62d3", "target_path": "apps/mobile,platform"},
    {"name": "vla", "source_repository": "https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator", "source_ref": "ai", "source_commit": "517df8f37105f659f2fe3561b46540ced830c731", "target_path": "ai/vla"}
  ]
}
```

The abbreviated objects above deliberately list only audited baseline metadata; the operational source of truth is the exact `source_commit=<actual-live-sha>` emitted by each Task 2–7 import block. Before saving the file, replace every baseline `source_commit` with that task's actual audited value and add the emitted `integration_commit` beside it. Never retain an old baseline when an explicitly approved ref advanced. Record any advancement in `source-map.md`, and validate that every final object has both 40-character hashes before committing.

Recover the exact integration hashes from their unique merge subjects if they were not copied during import:

```powershell
rtk git log --all -1 --format=%H --fixed-strings --grep="merge: import M33 firmware history"
rtk git log --all -1 --format=%H --fixed-strings --grep="merge: import M55 firmware history"
rtk git log --all -1 --format=%H --fixed-strings --grep="merge: import C8T6 sensor firmware history"
rtk git log --all -1 --format=%H --fixed-strings --grep="merge: import formal ROS2 workspace history"
rtk git log --all -1 --format=%H --fixed-strings --grep="merge: import rehabilitation app and platform history"
rtk git log --all -1 --format=%H --fixed-strings --grep="merge: import VLA prototype history"
```

Expected: each command prints exactly one 40-character integration merge commit SHA; use those six exact values in the corresponding `integration_commit` fields.

- [ ] **Step 2: 写历史回归测试**

Create `tools/test/test_history_provenance.py`:

```python
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_every_component_path_exists_and_exact_source_is_ancestor() -> None:
    data = json.loads((ROOT / "docs/migration/source-map.json").read_text("utf-8"))
    for component in data["components"]:
        for raw_path in component["target_path"].split(","):
            path = raw_path.strip()
            assert (ROOT / path).exists(), path
        source = component["source_commit"]
        integration = component["integration_commit"]
        assert len(source) == 40
        assert len(integration) == 40
        git("cat-file", "-e", f"{source}^{{commit}}")
        git("cat-file", "-e", f"{integration}^{{commit}}")
        subprocess.check_call(
            ["git", "merge-base", "--is-ancestor", source, "HEAD"], cwd=ROOT
        )
        assert git("rev-parse", f"{integration}^2") == source
```

- [ ] **Step 3: 写人类可读来源说明并运行测试**

Create `docs/migration/source-map.md` with a six-row table matching the JSON component list. Each row must show the exact source SHA and exact integration merge commit SHA. Explain that the source SHA is the integration commit's second parent, original hashes remain unchanged, and ordinary logs on new prefixed paths begin at the integration commit because older commits used source-root paths. Add an `Excluded material` section containing these exact classifications: temporary M33/M55 recovery branches require separate promotion; `NanoPi_ROSNode` direct CAN master is bench-only; old `APP` and its generated build tree are superseded; `ROS_VLA_WebSocket` is historical; farm-game and generated APK paths are excluded from the integrated platform tree.

Run:

```powershell
rtk python -m pytest tools/test/test_history_provenance.py -v
```

Expected: 所有目标路径存在；每个准确来源 SHA 都是 `HEAD` 的祖先，并且等于所记录集成提交的第二父提交。测试不要求 `git log --follow` 跨越前缀变化，也不限制迁移 worktree 中仍存在的本地临时分支。

- [ ] **Step 4: 提交来源映射**

Run:

```powershell
rtk git add docs/migration tools/test/test_history_provenance.py
rtk git commit -m "docs: record monorepo source provenance"
```

Expected: 提交成功。

## Task 9: 整理系统架构与协议导航

**Files:**
- Create: `docs/architecture/system-overview.md`
- Create: `docs/protocols/can-protocol.md`
- Create: `docs/protocols/m33-m55-ipc.md`
- Create: `docs/protocols/app-api.md`
- Create: `docs/protocols/safety-boundary.md`

- [ ] **Step 1: 从实现核对协议，不从旧 README 猜测**

Run:

```powershell
rtk rg -n "0x320|0x321|0x322|0x323|0x330|0x334" firmware/m33 ros/rehab_arm_ws
rtk rg -n "MSG_TYPE_SENSOR|MSG_TYPE_AI_INFERENCE|m33_m55" firmware/m33 firmware/m55
rtk rg -n "stream:on|ERR:readonly|6E400001" firmware/m33 apps/mobile platform/web
rtk rg -n "api/rehab-arm|training-sessions|agent/messages|devices/bind" platform/api platform/web apps/mobile
```

Expected: 为每份协议文档得到实际实现文件和测试位置。

- [ ] **Step 2: 写系统总览和四份协议入口**

`docs/architecture/system-overview.md` must contain these sections:

```markdown
# System overview
## Product layers
## Hardware and runtime ownership
## Formal motion path
## Telemetry and model-result path
## Mainline versus simulation and bench tools
## Current verified capability
## Known incomplete capability
```

Each `docs/protocols/*.md` must include: owner, consumers, direction, units/version, implementation links, tests, failure behavior, and safety restrictions. `safety-boundary.md` must state that M33 is the final safety authority and that BLE `move:*`, `mode:*`, and `stop` remain read-only in the current profile.

- [ ] **Step 3: 检查协议文档中的实现链接**

Run:

```powershell
rtk python -c "from pathlib import Path; import re; root=Path('.'); docs=list((root/'docs/protocols').glob('*.md')); missing=[]; [missing.append((str(d),p)) for d in docs for p in re.findall(r'`((?:firmware|ros|apps|platform)/[^`]+)`', d.read_text('utf-8')) if not (root/p).exists()]; assert not missing, missing"
```

Expected: 没有指向不存在路径的实现链接。

- [ ] **Step 4: 提交架构与协议文档**

Run:

```powershell
rtk git add docs/architecture docs/protocols
rtk git commit -m "docs: establish product architecture and protocol index"
```

Expected: 提交成功。

## Task 10: 编写新的项目 README

**Files:**
- Create: `README.md`
- Modify: component README files only when their old relative links are broken

- [ ] **Step 1: 写 README 内容守卫**

Extend `tools/test/test_repository_layout.py`:

```python
def test_root_readme_explains_the_complete_product() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    required = [
        "M33",
        "M55",
        "C8T6",
        "NanoPi",
        "ROS 2",
        "MuJoCo",
        "Android",
        "VLA",
        "JointTrajectory -> NanoPi -> M33",
        "当前已验证",
        "尚未完成",
        "安全边界",
        "目录结构",
        "构建入口",
    ]
    assert [item for item in required if item not in text] == []
```

- [ ] **Step 2: 运行测试确认 README 尚未满足要求**

Run:

```powershell
rtk python -m pytest tools/test/test_repository_layout.py::test_root_readme_explains_the_complete_product -v
```

Expected: FAIL，因为根 README 尚未创建或缺少必要章节。

- [ ] **Step 3: 编写完整中文 README**

Create `README.md` with this exact section order:

```markdown
# PSOC E84 智能康复机械臂
## 项目简介
## 系统架构
## 安全边界
## 当前已验证
## 尚未完成
## 目录结构
## 核心子系统
## 快速开始与构建入口
## 协议与文档
## 开发分类
## 测试与验证
## Git 历史与迁移来源
## 许可证与使用范围
```

The architecture section must show:

```text
App / Web / VLA / planner
  -> high-level request or JointTrajectory candidate
  -> NanoPi ROS2 bridge
  -> M33 local safety decision
  -> motors
```

The README must link to every top-level component and the four protocol documents, provide the shortest verified build command for each component, and distinguish `mainline`, `shadow-sim`, `dry-run`, `bench-debug`, `offline-demo`, and `side-channel`.

- [ ] **Step 4: 运行 README 和链接检查**

Run:

```powershell
rtk python -m pytest tools/test/test_repository_layout.py -v
rtk python -c "from pathlib import Path; import re; p=Path('README.md'); missing=[x for x in re.findall(r'\[[^]]+\]\(([^)]+)\)',p.read_text('utf-8')) if not x.startswith('http') and not Path(x.split('#')[0]).exists()]; assert not missing, missing"
```

Expected: README 内容守卫和本地链接检查通过。

- [ ] **Step 5: 提交 README**

Run:

```powershell
rtk git add README.md tools/test/test_repository_layout.py
rtk git commit -m "docs: introduce the PSOC E84 rehabilitation robot"
```

Expected: 提交成功。

## Task 11: 分工程构建与统一验证入口

**Files:**
- Create: `tools/test/verify_all.ps1`
- Create: `.github/workflows/repository-structure.yml`
- Create: `docs/validation/migration-validation.md`

- [ ] **Step 1: 逐个运行当前环境可执行的构建**

Run:

```powershell
rtk scons -C firmware/m33 -j4
rtk scons -C firmware/m55 -j4
rtk cmake --preset Debug -S firmware/c8t6
rtk cmake --build firmware/c8t6/build/Debug
rtk npm --prefix platform ci
rtk npm --prefix platform run build:web
rtk python -m pytest platform/api/tests -v
rtk npm --prefix apps/mobile ci
rtk npm --prefix apps/mobile run build:debug
rtk python -m pytest ai/vla/tests tools/test -v
```

Expected: 每个可用工具链的命令退出码为 0。ROS 2 必须在 Jazzy Linux 环境另行执行：

```bash
rtk colcon build --base-paths ros/rehab_arm_ws/src --symlink-install
rtk colcon test --base-paths ros/rehab_arm_ws/src
rtk colcon test-result --verbose
```

Expected: ROS build/test 通过。若当前机器缺少 ROS，不得声称通过；在 `docs/validation/ros-migration-validation.md` 记录具体缺失依赖和待运行命令。

Create `docs/validation/migration-validation.md` with a table containing one row for M33, M55, C8T6, ROS2, Web, API, Android, VLA, repository layout, history, secrets, and large files. Each row records the exact command, result (`pass`, `fail`, or `not-run`), execution environment, and evidence summary. `not-run` must include the missing tool or hardware condition.

- [ ] **Step 2: 写统一验证脚本**

Create `tools/test/verify_all.ps1`:

```powershell
$ErrorActionPreference = "Stop"

python -m pytest tools/test -v
python -m pytest ai/vla/tests -v
python -m pytest platform/api/tests -v
npm --prefix platform run build:web
npm --prefix apps/mobile run sync:web

$status = git status --short
if ($status) {
    throw "Verification generated tracked changes:`n$status"
}
```

- [ ] **Step 3: 创建无硬件 CI**

Create `.github/workflows/repository-structure.yml`:

```yaml
name: repository-structure

on:
  push:
    branches: [main]
  pull_request:

jobs:
  structure:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install pytest
      - run: python -m pytest tools/test -v
      - run: python -m pytest ai/vla/tests -v
```

- [ ] **Step 4: 运行统一验证并提交**

Run:

```powershell
rtk powershell -ExecutionPolicy Bypass -File tools/test/verify_all.ps1
rtk git add tools/test/verify_all.ps1 .github/workflows/repository-structure.yml docs/validation/migration-validation.md
rtk git commit -m "ci: add monorepo verification entrypoint"
```

Expected: 脚本通过；提交只含验证脚本、CI 和必要验证记录。

## Task 12: 最终审计并只推送 main

**Files:**
- Modify: `docs/migration/source-map.json` if refreshed source tips changed
- Modify: `docs/migration/source-map.md`
- Modify: `docs/validation/*`

- [ ] **Step 1: 检查分支、历史和工作树**

Run:

```powershell
rtk git branch --format="%(refname:short)"
rtk git status --short
rtk git log --graph --decorate --oneline -n 40
rtk python -m pytest tools/test/test_history_provenance.py -v
```

Expected: 当前分支为本地迁移 worktree 分支 `codex/monorepo-migration`，工作树干净；每个组件的准确原始 SHA 通过 merge 节点汇入当前历史；来源测试通过。此时不要求本地只有 `main`，因为临时 worktree 分支尚未收尾。

- [ ] **Step 2: 扫描秘密、大文件和禁止产物**

Run:

```powershell
rtk rg -n --hidden -g "!.git/**" -g "!*.md" "AKIA[0-9A-Z]{16}|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|api[_-]?key\s*[:=]\s*['\"][^'\"]+"
rtk powershell -NoProfile -Command "git ls-tree -r -l HEAD | ForEach-Object { if ($_ -match '^\d+ blob [0-9a-f]+\s+(\d+)\s+(.+)$' -and [int64]$matches[1] -gt 20971520) { $_ } }"
rtk python -m pytest tools/test/test_repository_layout.py -v
```

Expected: 无真实密钥；没有超过 20 MiB 的非预期 blob；无 APK、数据库、缓存或构建目录被跟踪。

- [ ] **Step 3: 快进本地 main 并移除临时 worktree/分支**

从原始仓库 checkout（不是即将删除的迁移 worktree）运行：

```powershell
rtk powershell -NoProfile -Command '$repo="F:\RT-ThreadStudio\workspace\PSOC_E84_robot"; $worktree="F:\RT-ThreadStudio\workspace\.worktrees\PSOC_E84_robot\monorepo-migration"; $branch="codex/monorepo-migration"; $current=(git -C $repo branch --show-current).Trim(); if($current -ne "main"){throw "Original checkout must be on main, got $current"}; $dirty=@(git -C $repo status --porcelain); if($dirty.Count){throw "Original main index/worktree is not clean: $dirty"}; $migrationTip=(git -C $repo rev-parse $branch).Trim(); if($migrationTip -notmatch "^[0-9a-f]{40}$"){throw "Invalid migration tip: $migrationTip"}; git -C $repo merge --ff-only $migrationTip; if($LASTEXITCODE){exit $LASTEXITCODE}; $mainTip=(git -C $repo rev-parse main).Trim(); if($mainTip -ne $migrationTip){throw "main $mainTip != saved migration tip $migrationTip"}; git -C $repo worktree remove $worktree; if($LASTEXITCODE){exit $LASTEXITCODE}; git -C $repo branch -d $branch; if($LASTEXITCODE){exit $LASTEXITCODE}; if((git -C $repo branch --show-current).Trim() -ne "main"){throw "Original checkout left main"}; $finalDirty=@(git -C $repo status --porcelain); if($finalDirty.Count){throw "Final main index/worktree is not clean: $finalDirty"}; Write-Output "main=$mainTip"'
```

Expected: 删除任何资源前先明确断言原始 checkout 位于 `main` 且 index/worktree（包括未跟踪文件）干净，并保存迁移 tip；`main` 仅以 `--ff-only` 快进，且精确等于该已保存 tip 后，才移除临时 worktree 和本地分支。最终仍位于干净的 `main`。

- [ ] **Step 4: 确认远端仍为空并只推送 main**

Run:

```powershell
rtk git -C F:\RT-ThreadStudio\workspace\PSOC_E84_robot ls-remote --heads origin
rtk git -C F:\RT-ThreadStudio\workspace\PSOC_E84_robot push -u origin main
rtk powershell -NoProfile -Command '$heads=@(git -C "F:\RT-ThreadStudio\workspace\PSOC_E84_robot" ls-remote --heads origin | ForEach-Object { ($_ -split "`t")[1] }); if($heads.Count -ne 1 -or $heads[0] -ne "refs/heads/main"){throw "Unexpected remote heads: $heads"}'
rtk git -C F:\RT-ThreadStudio\workspace\PSOC_E84_robot fetch origin main
rtk git -C F:\RT-ThreadStudio\workspace\PSOC_E84_robot diff --exit-code main origin/main
```

Expected: 推送前目标远端无 heads；只推送本地 `main`，绝不推送 `codex/monorepo-migration` 或任何 history/migration ref。推送后远端 heads 的精确集合为 `refs/heads/main`，且 `origin/main` 与本地 `main` 完全一致。
