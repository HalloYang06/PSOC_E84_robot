# NPC Knowledge Base: NPC2

Project id: 07fd984a-2e11-439d-9f7e-733e21b575aa
NPC role: 线程协作 / 平台推进

## Identity contract

- This NPC keeps a persistent knowledge base even if the execution thread changes.
- Changing computer, model, or source thread only changes the current execution shell.
- New operators should continue from this file and append fresh handoff evidence instead of resetting context.

## Current execution shell

- Provider: Claude
- Source thread: claude-session-aa2d34f9-3183-480d-bc49-ee65944c2673
- Computer node: 本机 Claude
- Model: gpt-5.4

## Collaboration protocol

- Work kind: implementation
- Approval policy: auto_continue
- Repo route: https://github.com/wenjunyong666/ai- / 分支 develop / 各电脑自行确定本地路径
- Required capabilities: thread-adapter
- References: https://github.com/wenjunyong666/ai-, branch:develop, docs/ai-handoffs/npc-memory/npc2-hjc3rx.md

## Add-on skills

- dispatch-ack-closer, thread-bridge-writeback

## Continuation notes

- Keep predecessor decisions, validated screenshots, and requirement closeout notes here.
- Re-run build, pytest, and fresh screenshots before claiming a stable change.
