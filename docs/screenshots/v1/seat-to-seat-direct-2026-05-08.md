# 同工位 NPC 互派验收报告

- 时间：2026-05-08T07:07:10.113Z → 2026-05-08T07:07:10.755Z
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
    "message_id": "c2116bc4-17e3-4475-8667-e25ffb898298",
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
    "message_id": "f3e5f952-5058-4263-b656-09376d2cf4c1",
    "status": "pending_review",
    "expect": "pending_review",
    "ok": true,
    "body_has_route_line": true
  }
]
```