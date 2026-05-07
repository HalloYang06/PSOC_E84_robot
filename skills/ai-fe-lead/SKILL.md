---
name: "ai-fe-lead"
description: "Build and coordinate the first-version frontend of the AI collaboration platform. Use when setting up the web app shell, route structure, shared components, page ownership, mock-data-first development, and mobile-safe execution."
---

# AI-FE-LEAD

Frontend mission:

1. Make the first-version UI usable on desktop and mobile.
2. Build the game-style research-base shell without blocking CRUD pages.
3. Allow mock-data-first progress while backend APIs mature.

Prioritize:

1. `/base`
2. `/projects`
3. `/agents`
4. `/runners`
5. `/tasks`
6. `/tasks/:id/diff`
7. `/tasks/:id/logs`
8. `/tasks/:id/context`
9. `/usage`
10. `/lab`

Rules:

- Keep text readable and stable on mobile.
- Use clear state colors and labels.
- Separate common components from page panels.
- Avoid decorative work that delays the closed loop.

Use this handoff format:

```text
【前端交接】
页面或组件:
当前状态:
使用数据源:
缺失接口:
剩余工作:
风险:
```

