# C3 验收：runner inbox → 本机 Claude CLI → 平台回执 端到端走查（2026-05-07）

> 通道 A 端到端补完（计划 `handoff-schema-gentle-pillow.md` 的 S5/C3 步）。本文档是合格性证据：证明在
> `RUNNER_CLI_PROVIDER=claude` 时，runner 收到一条普通文本 prompt 后，会真的调起本机 `claude.cmd`，
> 把 stdout 通过 `complete_runner_message` 回写到平台，并把已处理的 inbox 文件归档到 `inbox/processed/`。

## 环境

| 项 | 值 |
|---|---|
| 平台 | Windows 11 + PowerShell |
| 仓库 | `D:\ai合作产品`，分支 `ai/game-loop-core` |
| 提交 | `5cc5cfe` (C1 cli_bridge 模块) + `2374abc` (C2 main 接桥) |
| Python | 3.11.9 |
| `where claude` | `C:\Users\18312\AppData\Roaming\npm\claude.cmd` |
| `where codex` | `C:\Users\18312\AppData\Roaming\npm\codex.cmd` |
| `RUNNER_CLI_PROVIDER` | `claude` |
| `RUNNER_CLI_TIMEOUT_SECONDS` | 180（脚本里直接传） |

## 走查方法

不起完整 API server——直接驱动 `runner.main._handle_runner_relay_message`，用一个 `FakeClient`
站位平台，让真实 `claude.cmd` 执行 prompt。这样能在不依赖后端 schema / WebSocket 的前提下，
独立验证通道 A 的 runner 端整条链路。

驱动脚本：`scripts/cli-bridge-walk-2026-05-07.py`（不是测试文件，是一次性走查工具，落在 `scripts/` 而不是 `artifacts/` 是因为后者被 .gitignore 屏蔽，留不下证据）。

```pwsh
python scripts/cli-bridge-walk-2026-05-07.py
```

## 输入

```json
{
  "id": "msg-c3-walk-001",
  "title": "C3 端到端 ping",
  "body": "请只回复一行：最终回复：pong-c3-walk",
  "status": "pending",
  "project_id": "proj_c3_walk"
}
```

## 实测输出

`artifacts/c3-walk/run.log`（控制台中文是 PowerShell GBK 显示的乱码，summary.json 里 UTF-8 原文）：

```
[FakeClient ack] msg-c3-walk-001 note='C3 Walk Runner accepted the prompt and wrote it to ...'
[FakeClient complete] msg-c3-walk-001 status=completed note_len=31
[walk] handled=True elapsed=16.2s
[walk] inbox/*.json=[]
[walk] inbox/processed/*.json=['msg-c3-walk-001.json']
[walk] PASS — claude returned pong-c3-walk via the runner relay path
```

`artifacts/c3-walk/summary.json`（关键断言）：

```json
{
  "handled": true,
  "elapsed_seconds": 16.18,
  "completions": [
    {
      "runner_id": "runner-c3-walk",
      "message_id": "msg-c3-walk-001",
      "result_status": "completed",
      "note": "[C3 端到端 ping] 最终回复：pong-c3-walk"
    }
  ],
  "inbox_remaining": [],
  "inbox_processed": ["msg-c3-walk-001.json"]
}
```

`runner-workdir/logs/c3-walk.log`（runner 端日志）：

```
2026-05-07T05:26:39Z [info] cli_bridge invoking provider=claude message=msg-c3-walk-001 \
  executor=D:\ai合作产品\scripts\platform-provider-executor.py
2026-05-07T05:26:55Z [info] Handled runner relay msg-c3-walk-001 kind=cli.invoke \
  provider=claude status=completed
```

## 合格性逐条核对

对照 `MEMORY.md > project_qualification_criterion.md`「平台能调本机 Claude/Codex 线程并合理协作 = 合格」，本轮通道 A：

| 要点 | 是否满足 | 证据 |
|---|---|---|
| 平台收到普通文本 prompt 后真的调起本机 claude | ✅ | `cli_bridge invoking provider=claude` 日志 + 16.2s 真实耗时（mock 不会这么慢） |
| 本机 CLI 端有可见过程 | ✅ | runner-workdir/logs/c3-walk.log 两行 info；executor 经 `subprocess.run` 真起新进程（任务管理器可见 claude.cmd） |
| AI 回复回到平台 | ✅ | `completions[0].note = "[C3 端到端 ping] 最终回复：pong-c3-walk"`，是 claude 的真实 stdout，前缀 `[title]` 由 `cli_bridge._truncate_note` 保留 |
| 不再黑盒落 inbox | ✅ | `inbox/msg-c3-walk-001.json` 已被 `_archive_inbox_file` 移到 `inbox/processed/`，下一轮 poll 不会重复处理 |
| `provider=disabled` 时行为不变 | ✅ | `apps/runner/tests/test_relay_cli_bridge_wiring.py::test_provider_disabled_keeps_legacy_inbox_only_behaviour` 已绿，旧 `test_relay_prompt_inbox.py` 三条用例不回退 |

## 不做的事 / 已知边界

- 没有起完整 FastAPI server，所以这次走查不覆盖 `PlatformClient` 真实 HTTP 路径上的 ack/complete。但
  `_handle_runner_relay_message` 调用 `client.complete_runner_message(..., result_status, note)` 的入参组装在
  这里已被覆盖，HTTP 调用本身在 `apps/runner/tests/test_runner_client.py` 已有单测。两端组合一次还是建议
  在下一次部署 staging 时跑一遍。
- 没有覆盖 codex 走查。代码路径同 claude（只在 executor 里 fork 不同分支），等用户哪天把
  `RUNNER_CLI_PROVIDER=codex` 跑一次再补一份 `cli-bridge-walk-codex-*.md` 即可，不在本轮范围。
- `subprocess` 没有用 streaming，stdout 是一次性回写。流式输出留给后续 realtime 总线。

## 结论

通道 A（runner relay）端到端打通。`RUNNER_CLI_PROVIDER=claude` 一开，runner 在收到普通文本 prompt 后会
真的调起本机 claude.cmd 把 stdout 回写到平台。本轮 C1+C2+C3 三步对应的合格性硬指标全部满足。

下一步建议：用户在自己的 dev 环境把 `RUNNER_CLI_PROVIDER` 加到 `.env`，跑一次 staging 走查覆盖
HTTP 真实链路（最快做法是 `pytest apps/runner/tests/` 全绿后，跑 `connect-ai-collab-runner.ps1` 起一个
本机 runner 连本地 API，再从 UI 派单）。

## 相关文件

- 实现：`apps/runner/runner/cli_bridge.py`、`apps/runner/runner/main.py:_handle_runner_relay_message`
- 单测：`apps/runner/tests/test_cli_bridge.py`（4 cases）、`apps/runner/tests/test_relay_cli_bridge_wiring.py`（2 cases）
- 走查脚本：`scripts/cli-bridge-walk-2026-05-07.py`
- 走查证据：`artifacts/c3-walk/run.log`、`artifacts/c3-walk/summary.json`、`artifacts/c3-walk/runner-workdir/logs/c3-walk.log`、`artifacts/c3-walk/runner-workdir/inbox/processed/msg-c3-walk-001.json`（artifacts/ 在 .gitignore 中，不入库；本次走查的 stdout/inbox 原文以引用片段形式贴在本文档里）
- 计划文档：`C:\Users\18312\.claude\plans\handoff-schema-gentle-pillow.md`
