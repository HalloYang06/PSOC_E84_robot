---
name: "ai-arch"
description: "Define and protect first-version system boundaries for the AI collaboration platform. Use when deciding directory structure, module boundaries, API surface, model boundaries, and what must be postponed beyond the first version."
---

# AI-ARCH

Optimize for a stable first-version skeleton, not a perfect future platform.

Always decide:

1. What is required for the closed loop.
2. Which module owns the behavior.
3. Which directory should contain the code.
4. Which features are explicitly postponed.

Guardrails:

- Prefer `apps/web`, `apps/api`, `apps/runner`, `infra`.
- Keep `packages/shared` minimal and useful.
- Do not introduce plugin systems, multi-tenant logic, or complex orchestration in the first version.

When giving direction, produce:

```text
【架构裁决】
主题:
建议目录:
Owner:
接口边界:
第一版是否必须:
延期原因:
```

