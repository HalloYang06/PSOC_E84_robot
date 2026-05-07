---
name: "ai-runner-git"
description: "Implement the first-version runner and git execution path for the AI collaboration platform. Use when building runner registration, heartbeat, task pickup, workspace creation, limited execution, log upload, and safe git metadata/diff integration."
---

# AI-RUNNER-GIT

Own the execution lane.

Runner must support:

1. register
2. heartbeat
3. capability report
4. task pickup
5. workspace creation
6. limited command execution
7. log/result upload

Git must support:

1. task branch metadata
2. commit association
3. diff retrieval or placeholder-safe storage
4. rollback record entry

Never implement:

- forced push to protected branches
- automatic dangerous git operations
- automatic hardware control

Use this output format:

```text
【执行链路更新】
模块:
完成内容:
支持的命令或能力:
日志与结果回传状态:
需要人类确认:
```

