# AI 协作平台全面 QA - 2026-06-01

## 总架构文档

本轮 QA 以 `docs/platform-agent-operating-architecture.md` 为总架构合同。该文档定义了当前平台的核心对象、五个一级界面、P0 runner/dispatch 现实闭环、NPC 工作台边界、设备数据工作台收敛规则，以及旧数据工场 / AI 实验室 / 观测台入口的兼容跳转要求。

辅助参考：

- `docs/ai-requirements/platform-full-chain-audit-2026-05-10.md`
- `docs/ai-requirements/platform-closure-matrix-2026-05-10.md`
- `docs/npc-workbench-structure-contract.md`

## 云端基线

命令：

```powershell
python scripts/check_web_api_alignment.py --web-base http://106.55.62.122:3001 --api-base http://106.55.62.122:8011 --project-id fe9bd342-f5ef-4afe-9c73-e7caa2ed17dd
```

结果：

- 对齐检查通过。
- Web/API 指向同一 API 实例。
- 部署分支：`ai/game-loop-core`
- 部署 SHA：`7bae92a49168`
- `artifact_preview_route` 通过代理加载，返回预期 `ARTIFACT_NOT_FOUND`。

## 本地构建与后端测试

通过：

```powershell
cmd /d /s /c "npm --workspace apps/web run build"
python -m pytest apps/api/tests/test_task_dispatch.py apps/api/tests/test_requirement_autonomy_flow.py
```

结果：

- Web build 通过。
- 关键后端测试 `25 passed`。
- build 中仍有既有 React hook lint warnings，未阻塞构建：
  - `apps/web/app/projects/[id]/2d-upgrade/project-2d-upgrade-game.tsx`
  - `apps/web/app/projects/[id]/project-playable-shell.tsx`
  - `apps/web/app/projects/[id]/workbench/_components/npc-tile.tsx`

注意：

- 单独先跑 `node node_modules\typescript\bin\tsc --noEmit --incremental false -p apps\web\tsconfig.json` 时，如果 `.next/types` 残留了旧 include 且当前 `.next` 类型文件不存在，会先报 TS6053。
- 完整 `build:web` 生成 `.next/types` 后，再跑同一条 `tsc` 可以通过。
- 这属于验证顺序/构建产物状态问题，不是当前代码类型错误。

## 云端用户视角巡检

人工 Playwright 巡检路径：

- `/workbench`
- `/company`
- `/robotics`
- `/datasets`
- `/ai-lab`
- `/observability`
- `/skill-forge`

证据目录：

```text
C:\Users\18312\.codex\automations\ai-2\artifacts\full-qa-20260601\manual-cloud-pages\
```

结果：

- 所有页面非空。
- 桌面宽度未发现横向溢出。
- 未扫出用户界面禁用内部词：`adapter`, `bridge`, `session jsonl`, `source_thread`, `canonical`, `requested id`, `raw uuid`, `local path`。
- `/datasets` 已按架构合同跳转到 `/robotics?tab=dataset&from=legacy`。
- `/ai-lab` 已按架构合同跳转到 `/robotics?tab=chart&from=legacy`。
- `/observability` 已按架构合同跳转到 `/company?from=legacy`。

## 已通过的专项脚本

```powershell
python scripts/validate-cross-platform-runner-onboarding.py
python scripts/validate-platform-dispatch-evidence-cdp.py --web-base http://106.55.62.122:3001 --api-base http://106.55.62.122:8011 --project-id fe9bd342-f5ef-4afe-9c73-e7caa2ed17dd --login-email 3245056131@qq.com --login-password password --output-dir C:\Users\18312\.codex\automations\ai-2\artifacts\full-qa-20260601\dispatch-evidence
```

结果：

- 跨平台 runner 接入脚本静态检查通过。
- NPC 工作台派发证据页验证通过。
- NPC 工作台具备 tile、Need/Task tabs、执行电脑状态、回执/确认提示。
- 未发现内部词泄漏。

## 发现的问题

### P0: Runner 队列存在无法解释的陈旧命令

命令：

```powershell
python scripts/validate-runner-watch-queue-http.py --api-base http://106.55.62.122:8011 --project-id fe9bd342-f5ef-4afe-9c73-e7caa2ed17dd --login-email 3245056131@qq.com --login-password password --output-dir C:\Users\18312\.codex\automations\ai-2\artifacts\full-qa-20260601\runner-queue
```

结果：

- 电脑数：5
- 线程数：34
- 可接单 runner：1
- 阻塞 runner：4
- 陈旧 queued command：16
- 其中 14 条可解释为等待离线目标电脑恢复。
- 其中 2 条无法解释为离线目标电脑。

具体风险：

- 两条 `thread_scan_request` 已排队约 16821 分钟。
- 它们指向 `cloud-linux-main` 和 `codex-local-win-0518133234`，报告判断 `target_offline=false`，因此不应继续以普通 queued 状态沉积。

证据：

```text
C:\Users\18312\.codex\automations\ai-2\artifacts\full-qa-20260601\runner-queue\runner-watch-queue-http-report-20260601-095848.json
```

建议：

- 后端对 thread scan queue 增加过期收口：超过阈值且目标不离线时标为 `blocked` 或 `waiting_closeout`，并给用户“重新扫描 / 取消 / 重新绑定电脑”入口。
- 公司层和 NPC 工作台不要把这类历史 queued 继续当作当前可执行工作。

### P0: 云端电脑接入命令抽屉未按验证脚本预期渲染

命令：

```powershell
python scripts/validate-cloud-computer-onboarding-commands-cdp.py --web-base http://106.55.62.122:3001 --api-base http://106.55.62.122:8011 --project-id fe9bd342-f5ef-4afe-9c73-e7caa2ed17dd --login-email 3245056131@qq.com --login-password password --output-dir C:\Users\18312\.codex\automations\ai-2\artifacts\full-qa-20260601\cloud-onboarding
```

结果：

- 脚本创建临时电脑节点后进入主项目页。
- 页面加载完成，但未出现这些选择器：
  - `[data-token-command="computer-pairing"]`
  - `[data-token-linux-command="computer-pairing"]`
  - `[data-token-watch-command="computer-pairing"]`
  - `[data-token-desktop-watch-command="computer-pairing"]`
  - `[data-manager-drawer-kind="computer-threads"]`
- 页面只显示极简项目入口：`NPC 工作台 / Linux 开发板 / 能力工坊 / 公司层 / 隐藏游戏`。

证据：

```text
C:\Users\18312\.codex\automations\ai-2\artifacts\full-qa-20260601\cloud-onboarding\cloud-computer-onboarding-commands-debug-20260601-095848.json
C:\Users\18312\.codex\automations\ai-2\artifacts\full-qa-20260601\cloud-onboarding\cloud-computer-onboarding-commands-debug-20260601-095848.png
```

判断：

- 这可能是页面入口结构更新后，验证脚本仍按旧 `panel=team&tab=computers&drawer=computer-threads` 合同等待。
- 但从用户视角看，如果主页面无法稳定打开“接入电脑命令抽屉”，P0 接入闭环就不完整。

建议：

- 先确认当前主页面真实接入入口的 canonical URL 和 data attributes。
- 若产品入口已变，更新 `scripts/validate-cloud-computer-onboarding-commands-cdp.py`。
- 若入口确实丢失，恢复电脑接入抽屉，并保留 Windows/Linux 命令的稳定 data attributes。

### P1: 五工作台和专业工作台脚本落后于新架构跳转合同

失败脚本：

```powershell
python scripts/validate-five-workbench-click-chain-cdp.py ...
python scripts/validate-professional-surfaces-fullchain-cdp.py ...
```

失败原因：

- `validate-five-workbench-click-chain-cdp.py` 仍等待 `/observability` 页面保留“观测台 / 异常入口”等旧独立页面内容。
- `validate-professional-surfaces-fullchain-cdp.py` 仍等待 `/datasets` 页面保留“数据工场”旧独立页面内容。

实际云端行为：

- `/datasets` 跳转到设备数据工作台数据标注 tab。
- `/ai-lab` 跳转到设备数据工作台图表实验 tab。
- `/observability` 跳转到公司层。

判断：

- 当前产品行为符合 `docs/platform-agent-operating-architecture.md` 的收敛方向。
- 验证脚本需要升级为断言“旧入口跳转到 canonical 工作台 + 对应 tab / from=legacy”，而不是继续等待旧页面正文。

## QA 优先级建议

1. P0 修 thread scan 陈旧队列收口，避免用户看到无法解释的 queued 状态。
2. P0 修或更新云端电脑接入命令入口，保证 Windows/Linux 复制即运行命令可从云端页面稳定拿到。
3. P1 更新五工作台与专业工作台验证脚本，让脚本跟上新架构合同。
4. P1 梳理 `tsc` 独立运行依赖 `.next/types` 的问题，避免 clean workspace 下 QA 先报误导性 TS6053。
5. P2 清理现有 React hook lint warnings，降低后续真实回归噪音。

