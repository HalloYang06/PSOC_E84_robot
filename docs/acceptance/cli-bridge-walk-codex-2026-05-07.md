# 通道 A 验收（codex 版）：runner inbox → 本机 codex CLI → 平台回执 端到端走查（2026-05-07）

> 通道 A（runner relay · 整机接单）的 `provider=codex` 合格性证据。
> 通道 A `provider=claude` 见 [`cli-bridge-walk-2026-05-07.md`](./cli-bridge-walk-2026-05-07.md)。
> 通道 B `provider=codex` 见 [`thread-watcher-walk-codex-2026-05-07.md`](./thread-watcher-walk-codex-2026-05-07.md)。

## 环境

| 项 | 值 |
|---|---|
| 平台 | Windows 11 + PowerShell |
| 仓库 | `D:\ai合作产品`，分支 `ai/game-loop-core` |
| Python | 3.11.9 |
| `where codex` | `C:\Users\18312\AppData\Roaming\npm\codex.cmd` |
| `codex --version` | `codex-cli 0.114.0` |
| `WALK_PROVIDER` env | `codex`（本轮新增 env，缺省 `claude` 向后兼容）|
| `cli_timeout_seconds` | 600（codex 时自动拉到 600，claude 时仍 180）|
| API server | `http://127.0.0.1:8000`（uvicorn `apps/api/app/main.py`） |
| DB | `apps/api/ai_collab.db`（SQLite） |

## 走查方法

走查脚本：[`scripts/cli-bridge-http-walk-2026-05-07.py`](../../scripts/cli-bridge-http-walk-2026-05-07.py)（同一份脚本，本轮通过 `WALK_PROVIDER=codex` 切换）

```pwsh
$env:WALK_PROVIDER = "codex"; python scripts/cli-bridge-http-walk-2026-05-07.py
```

脚本流程（与 claude 版一致）：
1. `PlatformClient.register` 真发 HTTP，runner 入库 status=online
2. 直接 INSERT 一条 `runner_command`（recipient_type=runner, project_id=proj_ai_collab, status=pending）模拟"平台 UI 派单"
3. `PlatformClient.fetch_runner_inbox` 真发 GET `/api/runners/{id}/inbox` —— 取回 1 条
4. `_handle_runner_relay_message → cli_bridge → 真实 codex.cmd` 执行
5. `PlatformClient.complete_runner_message` 真发 POST `.../messages/{id}/complete` —— 写回 note

`provider=codex` 时 executor 走 `_run_codex` 路径（`scripts/platform-provider-executor.py:130-164`）：

```
codex exec -m gpt-5.4 --skip-git-repo-check --ephemeral --output-last-message <tmpfile> -
<prompt via stdin>
```

回复从 `--output-last-message` 写入的文件读，stdout 是 codex 自己的 reasoning/log 流（含 mcp / websocket 重连日志）。

## 输入

```python
WALK_PROVIDER = "codex"
RUNNER_ID = f"runner-c3-http-codex-{uuid.uuid4().hex[:6]}"
message_id = f"msg-c3-http-{uuid.uuid4().hex[:8]}"
body = "请只回复一行：最终回复：pong-c3-http"
title = "C3 HTTP 端到端 ping"
project_id = "proj_ai_collab"
```

## 实测输出

控制台关键片段（GBK 显示乱码已忽略，UTF-8 原文以 DB 为准）：

```
[walk] WALK_PROVIDER=codex CLI_TIMEOUT=600s
[walk] RUNNER_ID=runner-c3-http-codex-5e28b8

[walk step 1] register runner via real HTTP
  -> register response: {"data": {"id": "runner-c3-http-codex-5e28b8", ..., "status": "online", ...

[walk step 2] insert pending message id=msg-c3-http-000b6573 project=proj_ai_collab
  -> initial DB row: status=pending

[walk step 3] PlatformClient.fetch_runner_inbox via real HTTP
  -> inbox returned 1 messages, ids=['msg-c3-http-000b6573']

[walk step 4] _handle_runner_relay_message → cli_bridge → real codex
  -> handled=True elapsed=55.7s

[walk step 5] read DB to confirm complete_runner_message landed
  -> final DB row: status='completed'
  -> inbox after handler: 0 messages

[walk] PASS - full HTTP pipeline platform<->runner<->CLI verified
```

`artifacts/c3-http-walk/summary.json`（关键断言）：

```json
{
  "runner_id": "runner-c3-http-codex-5e28b8",
  "message_id": "msg-c3-http-000b6573",
  "elapsed_seconds": 55.74,
  "handled": true,
  "inbox_before_ids": ["msg-c3-http-000b6573"],
  "inbox_after_ids": [],
  "db_initial_status": "pending",
  "db_final_status": "completed",
  "inbox_dir_remaining": [],
  "inbox_dir_processed": ["msg-c3-http-000b6573.json", ...]
}
```

实测 DB 三条消息（UTF-8 原文）：

| message_type | sender → recipient | status | body |
|---|---|---|---|
| `runner_command` | human/c3-walk-tester → runner/runner-c3-http-codex-5e28b8 | **completed** | `请只回复一行：最终回复：pong-c3-http` |
| `runner_ack` | runner/runner-c3-http-codex-5e28b8 → human/c3-walk-tester | delivered | `C3 HTTP Walk 5e28b8 accepted the prompt and wrote it to D:\ai合作产品\artifacts\c3-http-walk\runner-workdir\inbox\msg-c3-http-000b6573.json.` |
| `runner_result` | runner/runner-c3-http-codex-5e28b8 → human/c3-walk-tester | **completed** | **`[C3 HTTP 端到端 ping] 最终回复：pong-c3-http`** |

第三条 `runner_result.body` 是 codex CLI 的真实输出，平台 UI 在线程消息池里拉到的就是这个。

## 合格性逐条核对

对照 [`MEMORY.md > project_qualification_criterion.md`](../../../.claude/projects/D--ai----/memory/project_qualification_criterion.md) 的合格性硬指标：

| 要点 | 是否满足 | 证据 |
|---|---|---|
| 平台收到指令后真的调起本机 codex | ✅ | 55.74s 真实耗时（mock 不会这么慢，且 codex 本机走 mcp + websocket 真实初始化）+ `where codex` 已确认 |
| 本机 CLI 端有可见过程 | ✅ | runner-workdir/logs/c3-http.log 有 `cli_bridge invoking provider=codex` info；executor `subprocess.run` 真起新进程；codex 自己 stdout 还流式打 mcp/websocket 重连日志（任务管理器可见 codex.cmd） |
| AI 回复回到平台 | ✅ | `runner_result.body = "[C3 HTTP 端到端 ping] 最终回复：pong-c3-http"`，是 codex 的真实 `--output-last-message` 文件内容直送平台 `complete_runner_message`，平台 UI 拉这个字段就是用户看到的 AI 回答 |
| 用户视角 1-3 步上手 | ✅ | 与 claude 版一致——只多一步 `set WALK_PROVIDER=codex` 切换；用户实际派单走平台 UI，不直接跑 walk 脚本 |
| `provider=codex` 与 `provider=claude` 切换 | ✅ | 同一份 walk 脚本，env 切换；codex 默认 model `gpt-5.4` 由 adapter 自动补（`platform-workstation-adapter.py:556-559`），用户无需关心 |

## 关键差异 claude vs codex

| 项 | claude | codex |
|---|---|---|
| executor 命令 | `claude -p <prompt>` | `codex exec -m gpt-5.4 --skip-git-repo-check --ephemeral --output-last-message <file> -` |
| 回复来源 | stdout 直接抓 | `--output-last-message` 写文件再读 |
| executor timeout | 180s | 420s |
| walk timeout | 180s | 600s（>executor + buffer）|
| 实测耗时 | 8-34s | 55.7s |
| stdout 噪音 | 安静 | 多（mcp 启动 + websocket reconnect 5 次后 fallback HTTPS） |

## 已知边界

- **codex stdout 有 WebSocket UTF-8 编码错误日志**：codex CLI 把 `D:\ai合作产品` 的中文转 header 时 UTF-8 → str 失败，会 reconnect 5 次再 fallback HTTPS 才拿到回复。这是 codex CLI 自己的问题（不是本仓库的），不影响最终回复抓取（`--output-last-message` 文件最终是对的）。如果以后需要更快 codex 响应，可以考虑把仓库放在纯 ASCII 路径下。
- **没覆盖 qwen provider**：qwen 在 executor 里有分支但本机未配置，留给后续走查。
- **没覆盖中文 prompt 长内容**：本轮 prompt 短文本走通，长 prompt（>1k tokens）行为留给真实业务流量验证。

## 回归（claude 路径不退化）

本轮脚本默认 `WALK_PROVIDER=claude` 时跑出来的结果与上一轮 `cli-bridge-walk-2026-05-07.md` 完全一致（status=completed、elapsed≈34s、3 条 DB 消息齐全）——证明 env 参数化没破坏 claude 路径。

## 结论

通道 A（runner relay）的 `provider=codex` 端到端打通：

- ✅ 55.74s 内完整流程：register → fetch inbox → invoke codex.cmd → write back result
- ✅ DB 三条消息齐全（runner_command completed + runner_ack delivered + runner_result completed），平台 UI 拉得到 codex 真实回答
- ✅ 用户切换 provider 只需 1 个 env（`WALK_PROVIDER=codex`），其余流程不变
- ✅ codex 默认 model `gpt-5.4` 由 adapter 自动补，用户无需关心

## 相关文件

- 走查脚本：[`scripts/cli-bridge-http-walk-2026-05-07.py`](../../scripts/cli-bridge-http-walk-2026-05-07.py)（本轮加 `WALK_PROVIDER` env）
- 走查证据：`artifacts/c3-http-walk/summary.json`（artifacts/ 在 .gitignore，不入库；引用片段已贴在本文档）
- claude 版本：[`cli-bridge-walk-2026-05-07.md`](./cli-bridge-walk-2026-05-07.md)
- 通道 B codex 版本：[`thread-watcher-walk-codex-2026-05-07.md`](./thread-watcher-walk-codex-2026-05-07.md)
- executor codex 实现：[`scripts/platform-provider-executor.py`](../../scripts/platform-provider-executor.py) 的 `_run_codex` (line 130-164)
- adapter codex 默认 model：[`scripts/platform-workstation-adapter.py`](../../scripts/platform-workstation-adapter.py) line 556-559
