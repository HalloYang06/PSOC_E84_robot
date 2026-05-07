# NPC Knowledge Base: Shared dispatch NPC 20260425-103716

Project id: e14b32d1-ffe4-49ab-978e-9bb3a48eeaa0
NPC role: 联机派工验证 NPC

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
- Required capabilities: web-game-ui, thread-adapter
- References: https://github.com/wenjunyong666/ai-, branch:develop, docs/ai-handoffs/npc-memory/shared-dispatch-npc-20260425-103716-xzivgd.md

## Add-on skills

- browser-game-ui-architect, frontend-skill

## Continuation notes

- Keep predecessor decisions, validated screenshots, and requirement closeout notes here.
- Re-run build, pytest, and fresh screenshots before claiming a stable change.
