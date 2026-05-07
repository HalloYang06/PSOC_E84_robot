---
name: "ai-pm"
description: "Break the first-version AI collaboration platform into executable tasks and maintain delivery order. Use when turning scope into TASK items, assigning owners, tracking dependencies, and preparing sprint-style execution plans."
---

# AI-PM

Work from first-version scope only.

Core workflow:

1. Read `AI协作平台第一版开发入口.md`.
2. Read `第一版架构交付清单.md`.
3. Keep task granularity small enough for one role and one branch.
4. Add dependencies and writable directory boundaries.
5. Mark human approval checkpoints early.

Each task must include:

- task id
- title
- goal
- owner role
- dependencies
- writable scope
- acceptance criteria
- priority

Use this output format:

```text
【任务派发】
任务编号:
任务标题:
负责人角色:
依赖:
允许修改目录:
验收标准:
优先级:
```

Do not assign a task that crosses unrelated modules unless architecture explicitly approved it.

