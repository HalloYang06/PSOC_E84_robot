---
name: "ai-review-qa"
description: "Review and validate first-version work on the AI collaboration platform. Use when checking acceptance criteria, finding missing tests, validating UI/API/runner behavior, and producing merge-readiness feedback with explicit risks."
---

# AI-REVIEW-QA

Review for shipping readiness, not style points.

Always check:

1. Does the change satisfy the task goal?
2. Does it stay inside writable scope?
3. Does it include or describe validation?
4. Does it introduce risk in auth, secrets, audit, git, or hardware?
5. Is the first-version scope still intact?

Use this report format:

```text
【审查结果】
对象:
结论:
已验证内容:
缺失测试:
主要风险:
是否建议合并:
是否需要人类确认:
```

