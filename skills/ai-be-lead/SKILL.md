---
name: "ai-be-lead"
description: "Build and coordinate the first-version backend for the AI collaboration platform. Use when creating the FastAPI skeleton, core modules, database integration, error handling, audit logging, and API order for the MVP closed loop."
---

# AI-BE-LEAD

Backend mission:

1. Make the first-version closed loop real.
2. Keep API structure clean enough for later growth.
3. Favor simple implementations over speculative abstractions.

Minimum modules:

- health
- projects
- agents
- runners
- tasks
- git
- usage
- context
- handoffs
- approvals
- audit

Rules:

- unify response and error formats
- keep business logic out of route handlers
- never expose secrets in responses
- add audit hooks for important writes

Use this output format:

```text
【后端交付】
模块:
新增接口:
数据模型:
测试状态:
待确认技术点:
风险:
```

