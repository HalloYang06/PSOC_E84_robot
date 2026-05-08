# NPC 自主合作验收报告

- 时间：2026-05-08T01:42:38.060Z → 2026-05-08T01:42:38.411Z
- 项目：proj_ai_collab
- 整体：✅ PASS


## 步骤

- ✓ **login**
- ✓ **fetch project** — `proj_ai_collab`
- ✓ **pick pair** — `{"upstream":"前端工位","upstream_node":"runner-pc1","downstream":"前端工位-副","downstream_node":"runner-pc1","cross_workstation":false}`
- ✓ **create parent requirement A** — `{"id":"34a61b92-04ca-4d2a-8413-f96b009a9d23"}`
- ✓ **dispatch parent A → NPC1**
- ✓ **create child requirement B (trigger=on_requirement_done)** — `{"id":"e2062bbd-bec2-4da5-b9d1-25ba36662e6a","dependency":"34a61b92-04ca-4d2a-8413-f96b009a9d23"}`
- ✓ **complete parent A (final-reply done)**
- ✓ **poll autonomous dispatch on B** — `{"message_id":"e66eaca9-c709-4701-8ac3-18c8c4f93d6d","sender_type":"agent","sender_id":"861ba0d8-922e-4fbe-9d45-1a4c6e835967","recipient_id":"a5aaf5c9-d36e-4679-8cb8-4fdf00cdd7ec","status":"queued","title":"[自主合作] [autonomous-collab] 父需求 1778204558169 → [autonomous-collab] 子需求 1778204558243"}`
- ✓ **assert sender_id=NPC1 (row_id or config_id)** — `{"got":"861ba0d8-922e-4fbe-9d45-1a4c6e835967"}`
- ✓ **assert recipient is downstream workstation**
- ✓ **assert same-workstation skip review** — `{"status":"queued"}`
- ✓ **assert watcher ack flips message to acked**

## 摘要

```json
{
  "cross_workstation": false,
  "auto_dispatch_message_id": "e66eaca9-c709-4701-8ac3-18c8c4f93d6d",
  "downstream_status": "queued"
}
```