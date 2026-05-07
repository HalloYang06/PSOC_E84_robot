# NPC Knowledge Base: 第二台电脑协作NPC-220224

Project id: c2a6c6df-c14e-40e8-beb2-cd02685686fd
NPC role: 负责验证前台新建项目后，第二台电脑线程可以直接经由 NPC 接单并回写回执。

## Identity contract

- This NPC keeps a persistent knowledge base even if the execution thread changes.
- Changing computer, model, or source thread only changes the current execution shell.
- New operators should continue from this file and append fresh handoff evidence instead of resetting context.

## Current execution shell

- Provider: Codex
- Source thread: member-codex-214513
- Computer node: ui-pc-b-214513
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
