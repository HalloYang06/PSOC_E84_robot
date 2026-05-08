# 任务队列并发原子化验收报告

- 时间：2026-05-08T01:42:36.940Z → 2026-05-08T01:42:37.226Z
- 项目：proj_ai_collab
- 并发数：5
- 整体：✅ PASS


## 步骤

- ✓ **login**
- ✓ **pick first workstation** — `{"name":"前端工位","config_id":"前端工位"}`
- ✓ **create agent_command (status=queued)** — `{"id":"ddc0fd74-24ac-48f4-b080-86f71365f7c6","status":"queued"}`
- ✓ **concurrent ack fanout** — `{"fanout":5,"ok200":1,"conflict409":4}`
- ✓ **assert exactly 1 success**
- ✓ **assert remaining are 409**
- ✓ **assert 409 error code = MESSAGE_ALREADY_CLAIMED**

## 响应分布

```json
[
  {
    "idx": 0,
    "status": 200,
    "took_ms": 106
  },
  {
    "idx": 1,
    "status": 409,
    "took_ms": 134
  },
  {
    "idx": 2,
    "status": 409,
    "took_ms": 115
  },
  {
    "idx": 3,
    "status": 409,
    "took_ms": 108
  },
  {
    "idx": 4,
    "status": 409,
    "took_ms": 147
  }
]
```