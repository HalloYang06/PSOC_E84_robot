# 任务队列并发原子化验收报告

- 时间：2026-05-08T01:14:32.000Z → 2026-05-08T01:14:32.384Z
- 项目：proj_ai_collab
- 并发数：5
- 整体：✅ PASS


## 步骤

- ✓ **login**
- ✓ **pick first workstation** — `{"name":"前端工位","config_id":"前端工位"}`
- ✓ **create agent_command (status=queued)** — `{"id":"0f15b3f1-f53f-4aba-9db3-d3870ba1b36c","status":"queued"}`
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
    "took_ms": 105
  },
  {
    "idx": 1,
    "status": 409,
    "took_ms": 109
  },
  {
    "idx": 2,
    "status": 409,
    "took_ms": 110
  },
  {
    "idx": 3,
    "status": 409,
    "took_ms": 111
  },
  {
    "idx": 4,
    "status": 409,
    "took_ms": 116
  }
]
```