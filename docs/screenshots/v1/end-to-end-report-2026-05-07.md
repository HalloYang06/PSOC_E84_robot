# 端到端 AI 真回 验收报告

运行：2026-05-07T16:26:24.219Z  ·  模式 = `watcher`  ·  超时 = 20s

项目: `proj_ai_collab`  ·  seat: `前端工位` (`前端工位`)  ·  provider: `?`

## 结论：❌ FAIL

| 断言 | 结果 | 说明 |
|---|---|---|
| 后端：90s 内出现 agent_result | ❌ FAIL | 20s 内未见 agent_result（mode=watcher）— watcher 可能没起、CLI 调用失败、或者 dispatch_id 未透传 |
| 前端：消息流页面可见 | ❌ FAIL | 后端没回，前端无意义 |

## 截图

- 派单前：![before](01-before-dispatch.png)
- 派单后：![after](02-after-reply.png)

## 派出的命令

- message_id: `2d5189f4-10ae-4372-bc85-fbfa28b2f6af`
- dispatch_id: `e2e-1778171153365-dmuyy`

## FAIL 排查清单

**预检失败：`adapter-config HTTP 404: {"error":{"code":"NOT_FOUND","message":"computer node does not exist","details":{}},"meta":{"request_id":"21ba731a02824875a38b160ef7f55687"}}`**

这通常表示 seat 配的 `computer_node_id` 和项目 computer_nodes 表里的 id 不一致（如 `runner_pc1` vs `runner-pc1`），到工作台 NPC 头部"改身份"修。

1. `scripts/start-thread-watcher.ps1` 是否真起来了？看 `(未起 watcher)`。
2. 本机 PATH 里有没有 `claude` / `codex`？
3. seat 的 `provider_id` 是不是 `claude` / `codex` / `qwen`？
4. 20s 太短？设 `POLL_TIMEOUT_MS=180000` 再跑。