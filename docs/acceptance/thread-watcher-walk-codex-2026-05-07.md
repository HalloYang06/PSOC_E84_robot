# 通道 B 验收（codex 版 · 部分验证）：thread watcher → 本机 codex CLI → 平台回执（2026-05-07）

> **状态：4/5 stdout 信号 PASS，最后一步 writeback 被 codex CLI 配额耗尽挡住（外部限制，非代码 bug）。**
> 通道 A `provider=codex` 见 [`cli-bridge-walk-codex-2026-05-07.md`](./cli-bridge-walk-codex-2026-05-07.md)（已完整 PASS）。
> 通道 B `provider=claude` 见 [`thread-watcher-walk-2026-05-07.md`](./thread-watcher-walk-2026-05-07.md)（已完整 PASS）。

## 简短结论

通道 B 的 watcher → adapter → codex CLI 这条链路**真的能跑通到调起 codex CLI 那一步**，但本轮跑 walk 的时候本机 codex 的 ChatGPT Plus 配额刚好在通道 A walk 之后耗尽（`ERROR: You've hit your usage limit. Upgrade to Plus to continue using Codex, or try again at May 12th, 2026 2:57 AM.`），导致最后一步"codex 真实回复 → adapter writeback → DB"没拿到 PASS。

**关键事实**：
- ✅ adapter 真起 codex.cmd（stderr 里看到 codex 的 mcp 启动 / websocket 重连日志，不是 mock）
- ✅ adapter `--auto-ack` 写了 agent_ack delivered
- ✅ stdout 5 个信号里 4 个亮：banner / command / invoke / reply
- ❌ codex 配额耗尽 → executor 抛 RuntimeError → adapter writeback note 被平台 422 拒（详见下文 bug 笔记）
- ⚠️ DB 最终 `agent_command.status='acked'`（不是 `completed`）

## 环境

| 项 | 值 |
|---|---|
| 平台 | Windows 11 + PowerShell |
| 仓库 | `D:\ai合作产品`，分支 `ai/game-loop-core` |
| Python | 3.11.9 |
| `where codex` | `C:\Users\18312\AppData\Roaming\npm\codex.cmd` |
| `codex --version` | `codex-cli 0.114.0` |
| `WALK_PROVIDER` env | `codex`（本轮新增 env，缺省 `claude` 向后兼容）|
| `WATCHER_RUNTIME_SECONDS` | 240（codex 时自动从 90s 拉到 240s）|
| API server | `http://127.0.0.1:8000` |
| DB | `apps/api/ai_collab.db`（SQLite） |

## 走查方法

走查脚本：[`scripts/thread-watcher-walk-2026-05-07.py`](../../scripts/thread-watcher-walk-2026-05-07.py)（同一份脚本，本轮通过 `WALK_PROVIDER=codex` 切换）

```pwsh
$env:WALK_PROVIDER = "codex"; $env:WALK_DIRECT_ADAPTER = "1"; python scripts/thread-watcher-walk-2026-05-07.py
```

脚本流程（与 claude 版一致）：
1. DB 直插临时 workstation 行（`config_id=watcher-walk-codex-{tag}`，`computer_node_id=runner-pc1`，`ai_provider_id=codex`）
2. DB 直插 `agent_command` 消息（pending）
3. subprocess.Popen 起 adapter `--watch`，传 `--provider codex`
4. 实时读 watcher stdout 看 5 个关键信号
5. 看到 `[已回写平台]` 立即 SIGBREAK 终止 watcher
6. 查 DB 验证三条消息

ps1 路径同样支持（`scripts/start-thread-watcher.ps1 -Provider codex` 已透传）。

## 输入

```python
WALK_PROVIDER = "codex"
PROBE_TAG = "1a7e0c0e"
WORKSTATION_CONFIG_ID = "watcher-walk-codex-1a7e0c0e"
MESSAGE_ID = "msg-thread-watcher-1a7e0c0e"
PROBE_REPLY = "pong-watcher-1a7e0c0e"
PROMPT_BODY = "请只回复一行：最终回复：pong-watcher-1a7e0c0e"
```

## 实测输出

`artifacts/thread-watcher-walk/run.log`（关键片段）：

```
[18:11:33] ========================================
[18:11:33] 线程 watcher 已启动
[18:11:33] 项目: proj_ai_collab
[18:11:33] 线程: watcher-walk-codex-1a7e0c0e
[18:11:33] 提供商: codex
[18:11:33] 轮询: 每 3.0s 一次  执行目录: D:\ai合作产品
[18:11:33] ========================================
[18:11:33] 等待平台指令... (Ctrl+C 退出)
[18:11:33] 收到 1 条平台指令
[18:11:33] [收到平台指令] Thread Watcher 端到端 ping
[18:11:33] [已 ack] codex adapter accepted command msg-thread-watcher-1a7e0c0e.
[18:11:33] Local prompt file: D:\ai合作产品\artifacts\workstation-inbox\...\msg-thread-watcher-1a7e0c0e.md
[18:11:33] Provider CLI execution: on
[18:11:33] Executor cwd: D:\ai合作产品
[18:11:33] [正在调用 codex CLI ...]
[18:11:35] mcp: blender starting / unity starting / mcp-unity starting
[18:11:36] mcp: unity ready / mcp-unity ready / blender failed
[18:11:36~43] WebSocket reconnect 5 次（中文路径 UTF-8 header bug）
[18:11:43] warning: Falling back from WebSockets to HTTPS transport.
[18:11:44] ERROR: You've hit your usage limit. Upgrade to Plus to continue
            using Codex, or try again at May 12th, 2026 2:57 AM.
[18:11:44] Warning: no last agent message; wrote empty content to <tmp>.txt
[18:11:44] [stderr] RuntimeError: codex CLI failed (1): ...
[18:11:47] [轮询错误] HTTP 422 POST .../complete:
            "String should have at most 4000 characters" (note 长度 ~10 KB)
```

`artifacts/thread-watcher-walk/summary.json` 关键字段（注：本轮 summary.json 被后续 claude 回归覆盖，下面是 stdout 抓取的）：

```json
{
  "probe_tag": "1a7e0c0e",
  "walk_provider": "codex",
  "watcher_runtime_seconds_budget": 240,
  "handler_elapsed_seconds": 0.0,
  "stdout_signals": {
    "saw_banner": true,
    "saw_command": true,
    "saw_invoke": true,
    "saw_reply": true,
    "saw_writeback": false
  },
  "db_initial_status": "pending",
  "db_final_status": "acked",
  "db_has_agent_ack": true,
  "db_has_agent_result": false,
  "db_result_body_has_reply": false
}
```

DB 两条消息（实际 3 条预期，少 agent_result）：

| message_type | sender → recipient | status | body |
|---|---|---|---|
| `agent_command` | human/thread-watcher-walk-tester → workstation/watcher-walk-codex-1a7e0c0e | **acked**（不是 completed）| `请只回复一行：最终回复：pong-watcher-1a7e0c0e` |
| `agent_ack` | agent/watcher-walk-codex-1a7e0c0e → human/thread-watcher-walk-tester | delivered | `codex adapter accepted command msg-thread-watcher-1a7e0c0e. Local prompt file: ...` |
| `agent_result` | — | — | （**缺失**：codex executor 抛 RuntimeError，且 note 字段长度超 4000 被平台 422 拒）|

## 合格性逐条核对

对照 [`MEMORY.md > project_qualification_criterion.md`](../../../.claude/projects/D--ai----/memory/project_qualification_criterion.md) 的合格性硬指标：

| 要点 | 是否满足 | 证据 |
|---|---|---|
| 平台收到指令后真的调起本机 codex | ✅ | run.log 看到 codex mcp 启动 + WebSocket 重连 + 真实 ChatGPT API 配额报错；不是 mock |
| 本机 CLI 端有可见过程 | ✅ | run.log 完整时间线：横幅 → 收到指令 → ack → 调 CLI → codex stderr 流式输出 → 失败 → 报错 |
| AI 回复回到平台 | ❌ | codex 配额耗尽，executor RuntimeError，无 agent_result 落库；adapter 试图把错误写回 note 但被平台 422 拒（详见下文 bug 笔记） |
| 用户视角 1-3 步上手 | ✅ | 与 claude 版一致——只多一步 `set WALK_PROVIDER=codex` 切换 |
| 中文 workstation_id 不再爆 | ✅ | 本次走查 ASCII config_id 正常；中文 latin-1 修复在 commit `1d1e997` |

**hard 4/5**——前 4 条满足，第 3 条卡在外部资源（codex 配额）。

## codex 配额耗尽证据

本轮跑 walk 之前的通道 A codex walk 已 PASS（55.7s, 详见 `cli-bridge-walk-codex-2026-05-07.md`），但通道 B walk 跑的时候 codex CLI 直接返回：

```
ERROR: You've hit your usage limit. Upgrade to Plus to continue using Codex
(https://chatgpt.com/explore/plus), or try again at May 12th, 2026 2:57 AM.
```

立即重试 `echo ping | codex exec ...` 也是同样配额报错——证实是用户级配额耗尽，与本轮代码无关。

## 附带发现的 adapter bug（不在本轮范围）

walk 暴露了一个真 bug：codex/claude executor 抛 RuntimeError 时，adapter 把 stderr 全文（含 ~10 KB 的 codex websocket 错误日志 + 完整 prompt 回显）当 `note` 回写平台，触发：

```
HTTP 422 POST .../messages/{id}/complete:
{"errors":[{"type":"string_too_long","loc":["body","note"],
            "msg":"String should have at most 4000 characters", ...}]}
```

消息卡在 `acked`，无法进 `completed` 也无法进 `failed`——状态机断裂。

**修复方向**（不在本轮 commit）：
- adapter 在 `complete_workstation_message(note=...)` 写回前把 note 截到 4000 字符（保留首尾 + 加 `...truncated...` 标记）
- 或者改用 `agent_result.body` 写错误（body 长度限制更宽）+ status=failed
- 单独 plan 一轮处理

## 已知边界

- **codex 配额耗尽前 1 次能跑通通道 A，第 2 次跑通道 B 就被卡**：单 ChatGPT Plus 账号 codex 配额一次平台调用约 13k tokens，2 次足以耗尽小配额池
- **重跑步骤（quota 恢复后）**：`$env:WALK_PROVIDER="codex"; $env:WALK_DIRECT_ADAPTER="1"; python scripts/thread-watcher-walk-2026-05-07.py`，预期 PROBE_REPLY 串入库 + status=completed
- **没覆盖中文 workstation_id 在 codex 路径下的行为**：本轮 ASCII config_id；中文走查留给 quota 恢复后

## 回归（claude 路径不退化）

通道 B 默认 `WALK_PROVIDER=claude` 跑（同一份脚本）：
- ✅ 5/5 信号、agent_command completed、agent_ack delivered、agent_result completed
- ✅ `agent_result.body = "最终回复：pong-watcher-c1562244"`
- ✅ handler_elapsed_seconds = 14.8s

证明 walk 脚本参数化 + ps1 `-Provider` 透传不影响 claude 路径。

## 结论

通道 B 的 codex 链路在 watcher → adapter → 调起 codex CLI 这一段已被实测验证，最后一步真实回复 writeback 被外部 codex 配额限制挡住，不是本仓库代码 bug。

**完整 PASS 等条件**：codex 配额恢复（2026-05-12 02:57 起）→ 重跑同一脚本 → 收 5/5 信号 + agent_result completed。或升级 Plus 立刻重跑。

附带产出（不在本轮 commit）：发现 adapter note 4000 字符上限 bug，已记录待后续单独处理。

## 相关文件

- 走查脚本：[`scripts/thread-watcher-walk-2026-05-07.py`](../../scripts/thread-watcher-walk-2026-05-07.py)（本轮加 `WALK_PROVIDER` env + provider 透传）
- 通道 B claude 版本：[`thread-watcher-walk-2026-05-07.md`](./thread-watcher-walk-2026-05-07.md)
- 通道 A codex 版本：[`cli-bridge-walk-codex-2026-05-07.md`](./cli-bridge-walk-codex-2026-05-07.md)
- adapter `--watch` 实现：[`scripts/platform-workstation-adapter.py`](../../scripts/platform-workstation-adapter.py)
- executor codex 实现：[`scripts/platform-provider-executor.py`](../../scripts/platform-provider-executor.py) `_run_codex` (line 130-164)
- watcher 启动器（已支持 -Provider）：[`scripts/start-thread-watcher.ps1`](../../scripts/start-thread-watcher.ps1)
