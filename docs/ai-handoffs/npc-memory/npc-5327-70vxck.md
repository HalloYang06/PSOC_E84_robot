# NPC Knowledge Base: 第二台电脑协作NPC-5327

Project id: 7f2d9a27-cecf-4e61-af25-3792c24971e6
NPC role: 负责在第二台电脑线程上接单并回写最小回执与最终回复。

## Identity contract

- This NPC keeps a persistent knowledge base even if the execution thread changes.
- Changing computer, model, or source thread only changes the current execution shell.
- New operators should continue from this file and append fresh handoff evidence instead of resetting context.

## Current execution shell

- Provider: Codex
- Source thread: member-codex-full-145327
- Computer node: ui-full-b-145327
- Model: gpt-5.4

## Collaboration protocol

- Work kind: implementation
- Approval policy: auto_continue
- Repo route: 仓库协作上下文待补
- Required capabilities: general-software
- References: none

## Add-on skills

- No add-on skills yet

## Continuation notes

- Keep predecessor decisions, validated screenshots, and requirement closeout notes here.
- Re-run build, pytest, and fresh screenshots before claiming a stable change.
