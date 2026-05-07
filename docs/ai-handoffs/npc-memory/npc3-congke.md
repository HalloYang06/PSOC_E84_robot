# NPC Knowledge Base: NPC3

Project id: 78c4d3d0-bdc3-4030-b456-d94915a6c8b1
NPC role: 线程协作 / 平台推进

## Identity contract

- This NPC keeps a persistent knowledge base even if the execution thread changes.
- Changing computer, model, or source thread only changes the current execution shell.
- New operators should continue from this file and append fresh handoff evidence instead of resetting context.

## Current execution shell

- Provider: Claude
- Source thread: claude-session-user-flow-writer-20260423-181944
- Computer node: user-flow-local-pc-20260423-181944
- Model: claude

## Collaboration protocol

- Work kind: implementation
- Approval policy: auto_continue
- Repo route: https://github.com/wenjunyong666/ai- / 分支 develop / 各电脑自行确定本地路径
- Required capabilities: thread-adapter
- References: https://github.com/wenjunyong666/ai-, branch:develop, docs/ai-handoffs/npc-memory/npc3-congke.md

## Add-on skills

- dispatch-ack-closer, thread-bridge-writeback

## Continuation notes

- Keep predecessor decisions, validated screenshots, and requirement closeout notes here.
- Re-run build, pytest, and fresh screenshots before claiming a stable change.
