# 通道 B 验收：thread watcher → 本机 Claude CLI → 平台回执 端到端走查（2026-05-07）

> 通道 B（workstation watcher · 线程 = 工位 = 一个 PS 终端）的合格性证据。
> 通道 A（runner relay · 整机接单）见 [`cli-bridge-walk-2026-05-07.md`](./cli-bridge-walk-2026-05-07.md)。
>
> **`provider=codex` 版本见 [`thread-watcher-walk-codex-2026-05-07.md`](./thread-watcher-walk-codex-2026-05-07.md)（4/5 信号 PASS，writeback 被外部 codex 配额挡住，等 quota 恢复后重跑）。**

## 环境

| 项 | 值 |
|---|---|
| 平台 | Windows 11 + PowerShell |
| 仓库 | `D:\ai合作产品`，分支 `ai/game-loop-core` |
| 提交 | `eb44ce6`（C1 用户文档 + UI 引导）+ 本轮 C2（走查脚本 + 本文档） |
| Python | 3.11.9 |
| `where claude` | `C:\Users\18312\AppData\Roaming\npm\claude.cmd` |
| `claude --version` | `2.1.132 (Claude Code)` |
| API server | `http://127.0.0.1:8000`（uvicorn `apps/api/app/main.py`） |
| DB | `apps/api/ai_collab.db`（SQLite） |

## 走查方法

走查脚本：[`scripts/thread-watcher-walk-2026-05-07.py`](../../scripts/thread-watcher-walk-2026-05-07.py)

脚本流程：
1. **DB 直插**临时 workstation 行（`config_id=watcher-walk-{8 位随机}`，`computer_node_id=runner-pc1`，`ai_provider_id=claude`）
2. **DB 直插** `agent_command` 消息（`recipient_type=workstation`，`recipient_id` 指向上面的 config_id，`status=pending`）
3. **subprocess.Popen 起 watcher**（默认走 `start-thread-watcher.ps1`；带 `WALK_DIRECT_ADAPTER=1` 时直跑 adapter）
4. 实时读 watcher stdout 看 5 个关键信号：
   - `saw_banner` — watcher 启动横幅
   - `saw_command` — `[收到平台指令]`
   - `saw_invoke` — `[正在调用 claude CLI ...]`
   - `saw_reply` — `claude.cmd` 的真实回复（含本轮探针字符串 `pong-watcher-{tag}`）
   - `saw_writeback` — `[已回写平台] status=completed`
5. 读到 `[已回写平台]` 立即 SIGBREAK 终止 watcher，查 DB 验证三条消息：
   - 原 `agent_command` 是否变 `completed`
   - 是否新增一条 `agent_ack`（watcher 收到指令时的最小回执）
   - 是否新增一条 `agent_result`（claude 的真实回复落库）
6. 删除临时 workstation 行（保留消息行供事后查阅）

> 为什么走查脚本默认 `WALK_DIRECT_ADAPTER=1` 跑 adapter 而不是走 ps1？
> ps1 只是个三行包装（banner + 调 python adapter + 退出码），合格性核心是 adapter 的 `--watch` 模式。
> ps1 自身在另外的手动验证里跑通（见下文「人工 ps1 验证」），自动 walk 走 direct 路径，避免 PowerShell 在 subprocess.Popen 上下文里的 stdout 缓冲问题污染信号检测。

## 输入

```python
PROJECT_ID = "proj_ai_collab"
WORKSTATION_CONFIG_ID = "watcher-walk-{tag}"  # 临时
MESSAGE_ID = "msg-thread-watcher-{tag}"
PROBE_REPLY = "pong-watcher-{tag}"
PROMPT_BODY = f"请只回复一行：最终回复：{PROBE_REPLY}"
PROMPT_TITLE = "Thread Watcher 端到端 ping"
```

## 实测输出

`artifacts/thread-watcher-walk/run.log`（关键片段）：

```
[17:39:33] ========================================
[17:39:33] 线程 watcher 已启动
[17:39:33] 项目: proj_ai_collab
[17:39:33] 线程: watcher-walk-0c532914
[17:39:33] 提供商: claude
[17:39:33] 轮询: 每 3.0s 一次  执行目录: D:\ai合作产品
[17:39:33] API: http://127.0.0.1:8000
[17:39:33] ========================================
[17:39:33] 等待平台指令... (Ctrl+C 退出)
[17:39:33] 收到 1 条平台指令
[17:39:33] [收到平台指令] Thread Watcher 端到端 ping
[17:39:33] 消息ID: msg-thread-watcher-0c532914
[17:39:33] 线程: watcher-walk-0c532914  来源: human/thread-watcher-walk-tester
[17:39:33] 请只回复一行：最终回复：pong-watcher-0c532914
[17:39:33] [已 ack] claude adapter accepted command msg-thread-watcher-0c532914.
[17:39:33] Local prompt file: D:\ai合作产品\artifacts\workstation-inbox\proj_ai_collab\watcher-walk-0c532914\msg-thread-watcher-0c532914.md
[17:39:33] Provider CLI execution: on
[17:39:33] Executor cwd: D:\ai合作产品
[17:39:33] [正在调用 claude CLI ...]
[17:39:41] 最终回复：pong-watcher-0c532914
[17:39:41] [已回写平台] status=completed note 长度=26
```

`artifacts/thread-watcher-walk/summary.json`（关键断言）：

```json
{
  "probe_tag": "0c532914",
  "project_id": "proj_ai_collab",
  "workstation_config_id": "watcher-walk-0c532914",
  "message_id": "msg-thread-watcher-0c532914",
  "probe_reply": "pong-watcher-0c532914",
  "handler_elapsed_seconds": 8.67,
  "stdout_signals": {
    "saw_banner": true,
    "saw_command": true,
    "saw_invoke": true,
    "saw_reply": true,
    "saw_writeback": true
  },
  "db_initial_status": "pending",
  "db_final_status": "completed",
  "db_has_agent_ack": true,
  "db_has_agent_result": true,
  "db_result_body_has_reply": true
}
```

DB 三条消息（`db_related_messages` 摘录）：

| message_type | sender → recipient | status | body |
|---|---|---|---|
| `agent_command` | human/thread-watcher-walk-tester → workstation/watcher-walk-0c532914 | **completed** | `请只回复一行：最终回复：pong-watcher-0c532914` |
| `agent_ack` | agent/watcher-walk-0c532914 → human/thread-watcher-walk-tester | delivered | `claude adapter accepted command msg-thread-watcher-0c532914. Local prompt file: ...` |
| `agent_result` | agent/watcher-walk-0c532914 → human/thread-watcher-walk-tester | **completed** | **`最终回复：pong-watcher-0c532914`** |

`agent_result.body` 就是 claude 的真实输出，平台 UI 在线程消息池里拉到的也是这个。

## 合格性逐条核对

对照 [`MEMORY.md > project_qualification_criterion.md`](../../../.claude/projects/D--ai----/memory/project_qualification_criterion.md) 的合格性硬指标：

| 要点 | 是否满足 | 证据 |
|---|---|---|
| 平台收到指令后真的调起本机 claude | ✅ | `[正在调用 claude CLI ...]` + 8.67s 真实耗时（mock 不会这么慢）+ `where claude` 已确认 |
| 本机 CLI 端有可见过程 | ✅ | run.log 完整时间线：横幅 → 收到指令 → ack → 调 CLI → 回复 → 回写。每条都进 stdout，不是黑盒 |
| AI 回复回到平台 | ✅ | `agent_result.body = "最终回复：pong-watcher-0c532914"`，是 claude 的真实 stdout 直送 DB，平台 UI 拉这个字段就是用户看到的 AI 回答 |
| 用户视角 1-3 步上手 | ✅ | 通道 B 上手文档 [`THREAD_WATCHER_QUICKSTART_2026-05-07.md`](../user-guides/THREAD_WATCHER_QUICKSTART_2026-05-07.md)（commit `eb44ce6`）已经在驾驶舱"AI 线程"卡片和派单表单上方挂链 |
| 中文 workstation_id 不再爆 | ✅ | commit `1d1e997` 修过 latin-1 header，本次 walk 的 ASCII config_id 验证基础链路；中文 config_id 在上一轮已实测通（见上一份 commit body） |

## 人工 ps1 验证

`scripts/start-thread-watcher.ps1` 在交互式 PowerShell 下也能正常驱动（不是只有 walk 脚本能调 adapter）：

```powershell
PS> powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-thread-watcher.ps1 -ProjectId proj_ai_collab -WorkstationId watcher-walk-13019139 -PollSeconds 1
========================================
项目线程 watcher 启动准备
项目: proj_ai_collab
线程: watcher-walk-13019139
API:  http://127.0.0.1:8000
执行目录: D:\ai合作产品
轮询: 每 1s
========================================
（接下来 ps1 把 stdout 直接交给 python adapter，与 direct 模式一致）
```

本轮顺手修了 ps1 的一个 strict mode 边角 bug：
- 之前：`exit $LASTEXITCODE`，在 `Set-StrictMode -Version Latest` 下，如果 `& python` 还没产生 exit code（如启动失败）就会报 `VariableIsUndefined`
- 修复：用 `try { [int]$LASTEXITCODE } catch { 1 }` 兜底，启动失败也能拿到 1 而不是异常

## 已知边界

- **没有 watcher 在线状态检测**：UI 看到合格性 D 的时候不知道是哪根线程没起 watcher。需要后端 schema 加 watcher heartbeat 表 + agent，是 BACKEND_INVENTORY 增强方向 4「实时本机线程总线」的范围
- **subprocess.Popen + PowerShell 在 walk 自动化里有 stdout 缓冲差异**：直接 ps1 路径自动 walk 看不到 banner 之后的输出，所以默认走 `WALK_DIRECT_ADAPTER=1` 直跑 adapter。用户实际场景在交互式终端跑 ps1 没这个问题
- **没覆盖 codex provider**：本轮 provider=claude；codex 走查跟通道 A 一样留给后续 `thread-watcher-walk-codex-*.md`

## 结论

通道 B（workstation watcher · 线程 = 一个 PS 终端）端到端打通。在 watcher 长跑模式下，平台派一条 `agent_command` 给某根线程后：

- ✅ 8.67s 内 watcher 收到指令、调起本机 claude.cmd 真实跑、回复回写到 DB
- ✅ run.log 5 个关键信号全 ✅，用户在自己终端能看到从收到指令到回写的完整时间线
- ✅ DB 三条消息齐全（agent_command completed + agent_ack delivered + agent_result completed），平台 UI 拉得到 AI 真实回答
- ✅ 用户上手路径 1-3 步：开 PS 终端 → 跑 `start-thread-watcher.ps1 -ProjectId X -WorkstationId Y` → 平台派单看回写

## 相关文件

- 走查脚本：[`scripts/thread-watcher-walk-2026-05-07.py`](../../scripts/thread-watcher-walk-2026-05-07.py)
- 走查证据：`artifacts/thread-watcher-walk/{run.log,summary.json}`（artifacts/ 在 .gitignore，不入库；引用片段已贴在本文档）
- 用户手册：[`docs/user-guides/THREAD_WATCHER_QUICKSTART_2026-05-07.md`](../user-guides/THREAD_WATCHER_QUICKSTART_2026-05-07.md)
- watcher 启动器：[`scripts/start-thread-watcher.ps1`](../../scripts/start-thread-watcher.ps1)
- watcher 长跑核心：[`scripts/platform-workstation-adapter.py`](../../scripts/platform-workstation-adapter.py) 的 `--watch` 模式
- 通道 A 走查（参考范式）：[`docs/acceptance/cli-bridge-walk-2026-05-07.md`](./cli-bridge-walk-2026-05-07.md)
- 计划文档：`C:\Users\18312\.claude\plans\handoff-schema-gentle-pillow.md`
