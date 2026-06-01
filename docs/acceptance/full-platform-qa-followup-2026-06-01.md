# AI 协作平台全面 QA 跟进复验 - 2026-06-01

本轮是在 `docs/acceptance/full-platform-qa-expanded-2026-06-01.md` 之后继续做的跟进 QA，重点复验并行 AI 已提交的修复，并继续扫描页面、runner、线程可见性、设备工作台和后端测试。

## 当前代码与云端状态

- 本地/远端 HEAD：`dd60423f Harden thread visibility validation`。
- 云端部署：`b3e00b2f137e / ai/game-loop-core / 2026-06-01T02:21:16Z`。
- 结论：云端已部署 `b3e00b2 Close completed thread scan queue items`，但尚未部署 `dd60423f Harden thread visibility validation`。
- 当前工作树仍有既有未提交项，未触碰：`BACKEND_INVENTORY.md`、`scripts/build-soft-copyright-docs.py`。

## 已复验通过

### Runner 陈旧队列 P0 已收敛

命令：

```powershell
python scripts/validate-runner-watch-queue-http.py --api-base http://106.55.62.122:8011 --project-id fe9bd342-f5ef-4afe-9c73-e7caa2ed17dd --strict
```

报告：

```text
C:\Users\18312\.codex\automations\ai-2\artifacts\full-qa-followup-20260601\runner-queue\runner-watch-queue-http-report-20260601-104107.json
```

结果：

- `queued_command_count=14`
- `stale_queued_command_count=14`
- `stale_waiting_for_offline_target_count=14`
- `stale_unexplained_command_count=0`
- `issues=[]`

判断：

- 上一轮 P0 中“2 条无法解释的陈旧 queued 命令”已被 `b3e00b2` 修掉。
- 仍有 14 条陈旧 queued，但全部解释为等待离线目标电脑恢复；这不是同一个 P0 阻塞，但 UI 仍应给用户清晰的重连/取消入口。

### 多电脑 / 多 runner 防抢隔离脚本已通过

命令：

```powershell
python scripts/validate-cloud-runner-workstation-isolation.py --api-base http://106.55.62.122:8011 --project-id fe9bd342-f5ef-4afe-9c73-e7caa2ed17dd
```

报告：

```text
C:\Users\18312\.codex\automations\ai-2\artifacts\full-qa-followup-20260601\runner-isolation\cloud-runner-workstation-isolation-report-20260601-104108.json
```

结果：`ok=true`、`issues=[]`。

判断：

- 上一轮 P0 中 pairing token 404 的多 runner 隔离脚本问题已修。
- 当前可证明错误 runner 不能读绑定给另一个 runner 的工作站 inbox。

### 云端接入命令仍通过

报告：

```text
C:\Users\18312\.codex\automations\ai-2\artifacts\full-qa-followup-20260601\cloud-onboarding\cloud-computer-onboarding-commands-report-20260601-104343.json
```

结果：`ok=true`、`issues=[]`。

### 云端用户/隔离回归仍通过

报告：

```text
C:\Users\18312\.codex\automations\ai-2\artifacts\full-qa-followup-20260601\cloud-user-ux-isolation\2026-06-01T02-41-46-899Z\report.json
```

结果：

- `ok=true`
- `issues=[]`
- `skipped=[]`
- 主入口、2D 入口、公司层、NPC 工作台、设备数据工作台、能力工坊、移动端入口、对比项目 robotics、外部账号项目列表、外部账号直开目标项目均非空、无横向溢出、无脚本禁词。
- NPC tile 点击后 `npcTileContractOk=true`。

### NPC 工作台派发证据仍通过

报告：

```text
C:\Users\18312\.codex\automations\ai-2\artifacts\full-qa-followup-20260601\dispatch-evidence\platform-dispatch-evidence-report-20260601-104658.json
```

结果：

- `has_tile=true`
- `has_need_task_tabs=true`
- `has_desktop_or_runner_state=true`
- `has_receipt_or_review_hint=true`
- `internal_terms=[]`

## 仍然存在的问题

### P0-1 线程可见性脚本仍无法跑通 pairing token

命令：

```powershell
python scripts/validate-computer-thread-visibility-http.py --web-base http://106.55.62.122:3001 --api-base http://106.55.62.122:8011 --project-id fe9bd342-f5ef-4afe-9c73-e7caa2ed17dd
```

报告：

```text
C:\Users\18312\.codex\automations\ai-2\artifacts\full-qa-followup-20260601\thread-visibility\computer-thread-visibility-http-report-20260601-104108.json
```

结果：

- 失败：`HTTP 404 POST ... /computer-nodes/thread-http-104108/pairing-token`
- 错误：`COMPUTER_NODE_NOT_FOUND`
- 清理检查：`synthetic_threads=0`、`synthetic_nodes=[]`

判断：

- `dd60423f` 已经让失败路径不再污染线程和电脑节点，这是进步。
- 但线程可见性验证仍无法进入“runner 注册 -> 同步线程 -> 页面可见”阶段。
- 因云端尚未部署 `dd60423f`，还不能判断这是云端版本落后还是本地脚本/API 仍不匹配；不过本地脚本已经在当前云端 API 上失败。

建议：

- 先部署 `dd60423f` 到云端再复跑。
- 如果部署后仍 404，检查电脑节点创建接口是否返回了不同的实际 node id；脚本必须用创建响应里的 id，而不是假设请求 id 一定被保留。

### P0-2 后端测试红灯仍未修

命令：

```powershell
python -m pytest apps/api/tests/test_runner_relay.py apps/api/tests/test_schema_surface_security.py apps/api/tests/test_task_professional_view.py
```

结果：

- `12 passed / 6 failed`
- 失败仍是上一轮同一组：
  - `test_runner_relay_command_accepts_structured_dispatch_id_without_legacy_body_hint`
  - `test_runner_relay_command_rejects_dispatch_from_another_project`
  - `test_security_write_schemas_do_not_expose_actor_or_status_fields`
  - `test_task_professional_view_aggregates_dispatch_messages_artifacts_and_audit`
  - `test_artifact_index_rejects_historical_alias_mismatch_even_when_source_message_id_matches`
  - `test_task_professional_view_summarizes_runner_capability_and_active_auto_retry`

判断：

- 派发测试仍期待未完成真实电脑/runner 可用性检查时返回 200，当前实现按 P0 合同返回 `409 TASK_DISPATCH_COMPUTER_UNBOUND`。
- `RunnerRelayCommandCreate` 仍暴露 `metadata`，安全 schema 测试仍红。

建议：

- 如果当前派发前置检查是正确架构，应更新测试 fixture：创建真实可派 runner/computer/seat，再断言 dispatch。
- 如果 `metadata` 是必要能力，应把 schema 安全测试改为 allowlist；否则收回外部写入口。

### P1-1 主页面资源中心 deep link 仍不稳定

报告：

```text
C:\Users\18312\.codex\automations\ai-2\artifacts\full-qa-followup-20260601\main-surface-sweep\surface-sweep-report-20260601-104343.md
```

结果：

- `/projects?tab=projects` 仍失败：找不到 `项目管理入口 / 我的项目`。
- `human-party` 被记录：`主角协作管理入口没有稳定落在当前页面`。
- 上一轮里 `development-workshop`、`npc-manager` 超时的问题这轮已变为 `ok`，说明有部分改善。

建议：

- 明确项目列表页当前用户态 marker，不要脚本继续等旧文案。
- 确认 `?panel=team&tab=human-party` 是否真的选中主角协作管理；如果只是停在资源中心头部，应修 tab 初始化。

### P1-2 协作消息池仍缺少二级定位栏

报告：

```text
C:\Users\18312\.codex\automations\ai-2\artifacts\full-qa-followup-20260601\main-surface-sweep\surface-sweep-report-20260601-104343.md
```

结果：

- `协作消息池缺少二级定位栏，结构可能退回旧形态。`

建议：

- 至少拆出：待人工确认、等待电脑恢复、最终结果、阻塞、历史积压。
- 或把消息池收成对象证据抽屉，主页面只保留摘要入口。

### P1-3 设备数据工作台专项脚本仍失效

命令：

```powershell
python scripts/validate-robotics-terminal-userwalk-cdp.py ...
python scripts/validate-robotics-debug-modes-cdp.py ...
```

结果：

- terminal userwalk 仍等待 `创建调试窗口`、`绑定真实设备` 超时。
- debug modes 仍等待 `/robotics` 和 debug mode 表达式超时。
- 通用 UX 回归能证明 `/robotics` 页面非空、无横向溢出、包含 `终端 / 数据标注 / 图表实验`，但不能证明三 tab 细链路。

建议：

- 更新专项脚本 marker 到当前设备数据工作台文案和选择器。
- 加入 tab 点击、只读/危险动作文案、窄屏布局验证。

### P1-4 用户可见旧口径仍残留

证据：

- 登录页文本仍包含：`人工审核、自动化开关、最终回复池都回到项目内`。
- 主页面仍显示：`运行评分 D (0.421)`。

判断：

- 云端 UX 禁词脚本没有覆盖登录页，且 `运行评分 D` 不在默认禁词里，所以通用回归不会抓到。

建议：

- 登录页改为 `人工确认`。
- `运行评分 D` 改为用户态状态，例如“运行状态需整理 / 查看改进建议”。

### P1-5 项目组织模型仍缺逻辑工位

API 摘要：

```json
{
  "computer_nodes": 5,
  "thread_workstations": 34,
  "workstations": 0,
  "ai_providers": 2,
  "offline_nodes": [
    "Windows 桌面电脑",
    "定向派单电脑 A 0517174653",
    "隔离验收电脑 B 0517194852",
    "Codex 本机 Windows 验收 13:32:34"
  ]
}
```

影响：

- NeedRouter 的同工位、跨工位、工位长、信任策略会缺组织依据。
- 公司层也难以形成真实部门态势图。

建议：

- 给现有项目补默认逻辑工位迁移，或在公司层提示“尚未建立部门/工位”并给一键生成入口。

## 当前通过但需持续观察

- `npm --workspace apps/web run build` 通过，但 React Hook warnings 仍在。
- `smoke_public_deployment.py` 通过。
- 账号/项目隔离通过。
- NPC 工作台结构和内部词检查通过。
- Linux/Windows 接入命令通过。

## 下一轮建议

1. 先把 `dd60423f` 部署到云端，再复跑 `validate-computer-thread-visibility-http.py`，确认线程扫描可见性脚本是否真正闭环。
2. 修后端 6 个测试：优先统一“真实派发前置检查”和测试 fixture，而不是绕过 P0 状态检查。
3. 更新设备数据工作台专项脚本，否则三 tab 设备闭环无法自动证明。
4. 修登录页旧口径和 `运行评分 D`，这是低风险高可见度的用户体验问题。
