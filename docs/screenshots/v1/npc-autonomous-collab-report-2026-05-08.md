# NPC 自主合作验收报告

- 时间：2026-05-08T01:15:14.175Z → 2026-05-08T01:15:14.536Z
- 项目：proj_ai_collab
- 整体：✅ PASS


## 步骤

- ✓ **login**
- ✓ **fetch project** — `proj_ai_collab`
- ✓ **pick pair** — `{"upstream":"前端工位","upstream_node":"runner-pc1","downstream":"前端工位-副","downstream_node":"runner-pc1","cross_workstation":false}`
- ✓ **create parent requirement A** — `{"id":"d3da256e-0fd9-4bc1-8b65-91d26df77c4a"}`
- ✓ **dispatch parent A → NPC1**
- ✓ **create child requirement B (trigger=on_requirement_done)** — `{"id":"32f2a07d-962a-4248-8e74-adb8237bcaaa","dependency":"d3da256e-0fd9-4bc1-8b65-91d26df77c4a"}`
- ✓ **complete parent A (final-reply done)**
- ✓ **poll autonomous dispatch on B** — `{"message_id":"04db3930-aaa3-440b-9536-333cf2f012f1","sender_type":"agent","sender_id":"861ba0d8-922e-4fbe-9d45-1a4c6e835967","recipient_id":"a5aaf5c9-d36e-4679-8cb8-4fdf00cdd7ec","status":"queued","title":"[自主合作] [autonomous-collab] 父需求 1778202914322 → [autonomous-collab] 子需求 1778202914406"}`
- ✓ **assert sender_id=NPC1 (row_id or config_id)** — `{"got":"861ba0d8-922e-4fbe-9d45-1a4c6e835967"}`
- ✓ **assert recipient is downstream workstation**
- ✓ **assert same-workstation skip review** — `{"status":"queued"}`

## 摘要

```json
{
  "cross_workstation": false,
  "auto_dispatch_message_id": "04db3930-aaa3-440b-9536-333cf2f012f1",
  "downstream_status": "queued"
}
```