# 同工位 NPC 互派验收报告

- 时间：2026-05-08T01:42:24.995Z → 2026-05-08T01:42:25.278Z
- 项目：proj_ai_collab
- 整体：✅ PASS


## 场景

```json
[
  {
    "mode": "same",
    "cross": false,
    "upstream": "前端工位",
    "downstream": "前端工位-副",
    "message_id": "e86634ed-5987-43ae-91c8-cd91f73551b0",
    "status": "queued",
    "expect": "queued",
    "ok": true,
    "body_has_route_line": true
  },
  {
    "mode": "cross",
    "cross": true,
    "upstream": "前端工位",
    "downstream": "执行工位",
    "message_id": "f91a72fe-db56-4489-8c18-e3e4931e42ee",
    "status": "pending_review",
    "expect": "pending_review",
    "ok": true,
    "body_has_route_line": true
  }
]
```