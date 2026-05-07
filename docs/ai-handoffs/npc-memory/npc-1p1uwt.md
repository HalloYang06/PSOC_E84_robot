# NPC Knowledge Base: 温俊勇

Project id: 78151f5f-f08c-4e83-b0fc-9be89263ecb3
NPC role: 找资料

## Identity contract

- This NPC keeps a persistent knowledge base even if the execution thread changes.
- Changing computer, model, or source thread only changes the current execution shell.
- New operators should continue from this file and append fresh handoff evidence instead of resetting context.

## Current execution shell

- Provider: Claude
- Source thread: claude-session-562dea0c-ac8e-4510-9f4d-c5dd223269ab
- Computer node: wjy
- Model: Sonnet 4.6

## Collaboration protocol

- Work kind: implementation
- Approval policy: auto_continue
- Project profile: software / 纯软件
- Token policy: 有界预算 / 单条 2500 / 单轮 8000 / 日预算 30000
- Runaway guard: 最多自动 3 轮 / 第 3 轮后人审 / 4 个停止条件
- Efficiency policy: 并发上限 2 / 先只读探针 / 相似任务合批
- Debug and simulation: 允许 AI 调试 / 可直接软件验证 / 无硬件写入限制
- Repo route: https://github.com/wenjunyong666/ai- / 分支 develop / 各电脑自行确定本地路径
- Required capabilities: thread-adapter
- References: https://github.com/wenjunyong666/ai-, branch:develop, docs/ai-handoffs/npc-memory/npc-8cmdq5.md, docs/ai-handoffs/npc-memory/npc-1p1uwt.md

## Safety boundaries

- Stop and ask for human review when the task crosses an approval boundary.
- For robot, embedded, serial, GPIO, firmware, or real-device work, simulate or do a read-only probe first.
- Do not keep spending tokens after the auto-round budget is reached; write a final reply or request review.

## Add-on skills

- No add-on skills yet

## Continuation notes

- Keep predecessor decisions, validated screenshots, and requirement closeout notes here.
- Re-run build, pytest, and fresh screenshots before claiming a stable change.
