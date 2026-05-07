# NPC Knowledge Base: NPC4

Project id: 1d243fb6-a146-4985-b6ab-a41ac30577a2
NPC role: 线程协作 / 平台推进

## Identity contract

- This NPC keeps a persistent knowledge base even if the execution thread changes.
- Changing computer, model, or source thread only changes the current execution shell.
- New operators should continue from this file and append fresh handoff evidence instead of resetting context.

## Current execution shell

- Provider: Claude
- Source thread: claude-session-2b1f84f6-b142-4f3f-8b3f-8650417d35a4
- Computer node: 本机 Claude
- Model: gpt-5.4

## Collaboration protocol

- Work kind: implementation
- Approval policy: auto_continue
- Repo route: https://github.com/wenjunyong666/ai- / 分支 develop / 各电脑自行确定本地路径
- Required capabilities: thread-adapter
- References: https://github.com/wenjunyong666/ai-, branch:develop, docs/ai-handoffs/npc-memory/npc4-7tytcv.md

## Add-on skills

- dispatch-ack-closer, thread-bridge-writeback

## Continuation notes

- Keep predecessor decisions, validated screenshots, and requirement closeout notes here.
- Re-run build, pytest, and fresh screenshots before claiming a stable change.
