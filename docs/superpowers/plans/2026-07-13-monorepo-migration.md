# PSOC E84 Robot Monorepo Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 M33、M55、C8T6、正式 ROS2、康复 App/平台和 VLA 的有效代码与主线历史迁入 `HalloYang06/PSOC_E84_robot` 的单一 `main`，并交付可导航、可验证的新 README。

**Architecture:** 每个来源分支先在隔离副本中用 `git-filter-repo` 重写到目标子目录，再以不相关历史合并的方式汇入目标仓库。固件保持三个独立构建工程；ROS 只保留正式 workspace；`ai-` 迁入康复 App、平台及其依赖闭包，并删除当前树中的农场游戏内容。最终执行结构、历史、构建、安全边界和秘密扫描后，只推送 `main`。

**Tech Stack:** Git、git-filter-repo、PowerShell、Python 3.12/pytest、RT-Thread/SCons、ROS 2 Jazzy/colcon、Node.js/Next.js、FastAPI、Capacitor/Gradle、GitHub Actions。

---

## 文件结构锁定

本计划创建或修改的仓库级文件：

- `.gitignore`：统一忽略固件、ROS、Node、Python、Android 和本地数据库输出。
- `.gitattributes`：固定文本换行策略，并把固件二进制资源标成 binary。
- `README.md`：完整项目入口。
- `docs/migration/source-map.md`：人类可读来源与迁移结果。
- `docs/migration/source-map.json`：机器可读来源、原提交和重写后提交。
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

## Task 1: 建立迁移防护与工具依赖

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

Expected: 本地分支为 `main`，只有计划/设计文档改动；目标远端仍无分支。

- [ ] **Step 2: 安装并验证历史重写工具**

Run:

```powershell
rtk python -m pip install "git-filter-repo==2.47.0"
rtk python -m git_filter_repo --version
```

Expected: 输出 `git-filter-repo` 版本，命令退出码为 0。

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

## Task 2: 带历史迁入 M33

**Files:**
- Import: `firmware/m33/**`
- Modify: `docs/migration/source-map.md`
- Modify: `docs/migration/source-map.json`

- [ ] **Step 1: 创建 M33 隔离副本并固定来源提交**

Run:

```powershell
rtk git clone --single-branch --branch M33 https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator.git F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\m33
rtk git -C F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\m33 rev-parse HEAD
```

Expected: HEAD 为执行时确认的正式 M33 基线；若不再是设计中的 `24bae363`，先审计新增提交并更新 source map，不能静默继续。

- [ ] **Step 2: 将完整 M33 历史重写到目标路径**

Run:

```powershell
rtk python -m git_filter_repo --source F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\m33 --target F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\m33-filtered --to-subdirectory-filter firmware/m33 --force
```

Expected: `m33-filtered` 的每个历史提交均位于 `firmware/m33/` 下，作者和提交说明保留。

- [ ] **Step 3: 把重写历史合入本地 main**

Run:

```powershell
rtk git remote add migration-m33 F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\m33-filtered
rtk git fetch migration-m33
rtk git merge --allow-unrelated-histories --no-ff migration-m33/M33 -m "merge: import M33 firmware history"
rtk git remote remove migration-m33
```

Expected: `firmware/m33/SConstruct` 和 `firmware/m33/applications/main.c` 存在，合并提交有 M33 重写历史作为父历史。

- [ ] **Step 4: 校验内容与历史**

Run:

```powershell
rtk powershell -NoProfile -Command "$source=(git -C 'F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\m33' ls-tree -r HEAD | ForEach-Object { $_ }); $target=(git ls-tree -r HEAD:firmware/m33 | ForEach-Object { $_ }); if((Compare-Object $source $target).Count){exit 1}"
rtk git log --follow --format="%an|%ad|%s" --date=short -- firmware/m33/applications/main.c
```

Expected: tree 对比退出码为 0；关键文件显示多条迁移前历史，而非只有一个导入提交。

## Task 3: 带历史迁入 M55

**Files:**
- Import: `firmware/m55/**`

- [ ] **Step 1: 创建并核对 M55 隔离副本**

Run:

```powershell
rtk git clone --single-branch --branch M55 https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator.git F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\m55
rtk git -C F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\m55 rev-parse HEAD
```

Expected: HEAD 为正式 `M55` 基线；WEN 临时延迟分支不自动替代它。

- [ ] **Step 2: 重写并合并 M55 历史**

Run:

```powershell
rtk python -m git_filter_repo --source F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\m55 --target F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\m55-filtered --to-subdirectory-filter firmware/m55 --force
rtk git remote add migration-m55 F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\m55-filtered
rtk git fetch migration-m55
rtk git merge --allow-unrelated-histories --no-ff migration-m55/M55 -m "merge: import M55 firmware history"
rtk git remote remove migration-m55
```

Expected: `firmware/m55/SConstruct`、M55 applications 和完整父历史存在。

- [ ] **Step 3: 校验 M55 tree 与关键文件历史**

Run:

```powershell
rtk powershell -NoProfile -Command "$source=(git -C 'F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\m55' ls-tree -r HEAD); $target=(git ls-tree -r HEAD:firmware/m55); if((Compare-Object $source $target).Count){exit 1}"
rtk git log --follow --oneline -- firmware/m55/applications/main.c
```

Expected: tree 完全一致，关键文件有连续历史。

## Task 4: 带历史迁入 C8T6

**Files:**
- Import: `firmware/c8t6/**`

- [ ] **Step 1: 克隆、重写和合并 C8T6**

Run:

```powershell
rtk git clone --single-branch --branch C8T6 https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator.git F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\c8t6
rtk python -m git_filter_repo --source F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\c8t6 --target F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\c8t6-filtered --to-subdirectory-filter firmware/c8t6 --force
rtk git remote add migration-c8t6 F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\c8t6-filtered
rtk git fetch migration-c8t6
rtk git merge --allow-unrelated-histories --no-ff migration-c8t6/C8T6 -m "merge: import C8T6 sensor firmware history"
rtk git remote remove migration-c8t6
```

Expected: C8T6 工程进入 `firmware/c8t6/`，历史为 `main` 的祖先。

- [ ] **Step 2: 校验 C8T6 内容和历史**

Run:

```powershell
rtk powershell -NoProfile -Command "$source=(git -C 'F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\c8t6' ls-tree -r HEAD); $target=(git ls-tree -r HEAD:firmware/c8t6); if((Compare-Object $source $target).Count){exit 1}"
rtk git log --follow --oneline -- firmware/c8t6
```

Expected: tree 对比通过并能看到来源历史。

## Task 5: 带历史迁入正式 ROS2 workspace

**Files:**
- Import: `ros/rehab_arm_ws/**`
- Create: `ros/rehab_arm_ws/src/rehab_arm_bringup/test/test_mainline_boundaries.py`
- Create: `tools/bench-debug/legacy-5dof/README.md`

- [ ] **Step 1: 只筛选正式 workspace 历史**

Run:

```powershell
rtk git clone --single-branch --branch feature/rehab-arm-ros2-architecture https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator.git F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\ros
rtk python -m git_filter_repo --source F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\ros --target F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\ros-filtered --path rehab_arm_ros2_ws/ --path-rename rehab_arm_ros2_ws/:ros/rehab_arm_ws/ --force
```

Expected: 旧根级 HTTP bridge、`ROS_VLA_WebSocket` 和 NanoPi 早期 workspace 不在过滤结果中。

- [ ] **Step 2: 合并正式 ROS 历史**

Run:

```powershell
rtk git remote add migration-ros F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\ros-filtered
rtk git fetch migration-ros
rtk git merge --allow-unrelated-histories --no-ff migration-ros/feature/rehab-arm-ros2-architecture -m "merge: import formal ROS2 workspace history"
rtk git remote remove migration-ros
```

Expected: `ros/rehab_arm_ws/src/rehab_arm_psoc_bridge`、6DOF description 和 MuJoCo 包存在。

- [ ] **Step 3: 先写正式入口边界测试**

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

- [ ] **Step 4: 运行边界测试并补充隔离说明**

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

- [ ] **Step 5: 提交 ROS 边界守卫**

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

- [ ] **Step 1: 刷新 `ai-` 康复分支并固定基线**

Run:

```powershell
rtk git clone --single-branch --branch app/rehab-arm-mobile-stitch https://github.com/wenjunyong666/ai-.git F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\rehab-platform
rtk git -C F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\rehab-platform rev-parse HEAD
```

Expected: HEAD 不早于审计基线 `f6c2c026`；新增提交先阅读后再固定 source map。

- [ ] **Step 2: 过滤并重命名 App/平台路径**

Run:

```powershell
rtk python -m git_filter_repo --source F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\rehab-platform --target F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\rehab-platform-filtered --path apps/mobile/rehab-arm-android/ --path apps/web/ --path apps/api/ --path apps/runner/ --path packages/shared/ --path infra/ --path package.json --path package-lock.json --path-rename apps/mobile/rehab-arm-android/:apps/mobile/ --path-rename apps/web/:platform/web/ --path-rename apps/api/:platform/api/ --path-rename apps/runner/:platform/runner/ --path-rename packages/shared/:platform/shared/ --path-rename infra/:platform/deploy/ --path-rename package.json:platform/package.json --path-rename package-lock.json:platform/package-lock.json --force
rtk python -m git_filter_repo --source F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\rehab-platform-filtered --target F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\rehab-platform-clean --path platform/web/public/harvest-moon-phaser3-game/ --path "platform/web/app/projects/[id]/2d-upgrade/" --path platform/web/lib/game/ --path-glob "platform/web/public/downloads/rehab-arm/*.apk" --invert-paths --force
```

Expected: `rehab-platform-clean` 当前 tree 只包含 App、平台运行闭包和对应历史，不含 `docs/screenshots`、APK、Harvest Moon 静态游戏、2D upgrade 游戏页和 `lib/game`。

- [ ] **Step 3: 合并 App/平台历史**

Run:

```powershell
rtk git remote add migration-platform F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\rehab-platform-clean
rtk git fetch migration-platform
rtk git merge --allow-unrelated-histories --no-ff migration-platform/app/rehab-arm-mobile-stitch -m "merge: import rehabilitation app and platform history"
rtk git remote remove migration-platform
```

Expected: App、Web、API、Runner、shared 和 deploy 均位于目标目录。

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

- [ ] **Step 1: 过滤旧 `ai` 分支的 VLA 系统历史**

Run:

```powershell
rtk git clone --single-branch --branch ai https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator.git F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\vla
rtk python -m git_filter_repo --source F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\vla --target F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\vla-filtered --path vla_system/ --path-rename vla_system/:ai/vla/ --force
rtk git remote add migration-vla F:\RT-ThreadStudio\workspace\PSOC_E84_robot-migration\vla-filtered
rtk git fetch migration-vla
rtk git merge --allow-unrelated-histories --no-ff migration-vla/ai -m "merge: import VLA prototype history"
rtk git remote remove migration-vla
```

Expected: VLA schema、验证器和测试在 `ai/vla/`，没有电机/CAN 直控实现。

- [ ] **Step 2: 写权限说明并运行原有测试**

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

- [ ] **Step 3: 提交 VLA 边界说明**

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

Create `docs/migration/source-map.json` with the actual refreshed full hashes captured in Tasks 2–7:

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

If a refreshed official ref advanced, replace only that component's `source_commit` with the audited full hash and record the change in `source-map.md`.

- [ ] **Step 2: 写历史回归测试**

Create `tools/test/test_history_provenance.py`:

```python
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_every_component_path_exists_and_has_history() -> None:
    data = json.loads((ROOT / "docs/migration/source-map.json").read_text("utf-8"))
    for component in data["components"]:
        for raw_path in component["target_path"].split(","):
            path = raw_path.strip()
            assert (ROOT / path).exists(), path
            assert int(git("rev-list", "--count", "HEAD", "--", path)) > 1, path


def test_target_remote_has_no_non_main_local_branch_plan() -> None:
    branches = git("branch", "--format=%(refname:short)").splitlines()
    assert branches == ["main"]
```

- [ ] **Step 3: 写人类可读来源说明并运行测试**

Create `docs/migration/source-map.md` with a six-row table matching the JSON component list. Add an `Excluded material` section containing these exact classifications: temporary M33/M55 recovery branches require separate promotion; `NanoPi_ROSNode` direct CAN master is bench-only; old `APP` and its generated build tree are superseded; `ROS_VLA_WebSocket` is historical; farm-game and generated APK paths are excluded from the platform filter.

Run:

```powershell
rtk python -m pytest tools/test/test_history_provenance.py -v
```

Expected: 所有目标路径有多条历史，且本地最终分支列表只有 `main`。

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

Expected: 本地只有 `main`；工作树干净；组件历史通过 merge 节点汇入 `main`；来源测试通过。

- [ ] **Step 2: 扫描秘密、大文件和禁止产物**

Run:

```powershell
rtk rg -n --hidden -g "!.git/**" -g "!*.md" "AKIA[0-9A-Z]{16}|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|api[_-]?key\s*[:=]\s*['\"][^'\"]+"
rtk powershell -NoProfile -Command "git ls-tree -r -l HEAD | ForEach-Object { if ($_ -match '^\d+ blob [0-9a-f]+\s+(\d+)\s+(.+)$' -and [int64]$matches[1] -gt 20971520) { $_ } }"
rtk python -m pytest tools/test/test_repository_layout.py -v
```

Expected: 无真实密钥；没有超过 20 MiB 的非预期 blob；无 APK、数据库、缓存或构建目录被跟踪。

- [ ] **Step 3: 确认远端仍为空且只推送 main**

Run:

```powershell
rtk git ls-remote --heads origin
rtk git push -u origin main
```

Expected: 推送前无远端 heads；推送后只有 `refs/heads/main`。

- [ ] **Step 4: 远端回读验证**

Run:

```powershell
rtk git ls-remote --symref origin HEAD
rtk git ls-remote --heads origin
rtk git fetch origin main
rtk git diff --exit-code main origin/main
```

Expected: `origin/main` 与本地 `main` 完全一致，远端没有迁移或 history 分支。
