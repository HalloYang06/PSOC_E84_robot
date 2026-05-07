# NPC 自主合作验收报告

- 时间：2026-05-07T18:04:34.850Z → 2026-05-07T18:04:35.140Z
- 项目：proj_ai_collab
- 整体：✅ PASS


## 步骤

- ✓ **login**
- ✓ **fetch project** — `proj_ai_collab`
- ✓ **pick pair** — `{"upstream":"前端工位","upstream_node":"runner-pc1","downstream":"前端工位-副","downstream_node":"runner-pc1","cross_workstation":false}`
- ✓ **create parent requirement A** — `{"id":"a1baaa37-ab88-44f1-93b8-31b84b7f7cbb"}`
- ✓ **dispatch parent A → NPC1**
- ✓ **create child requirement B (trigger=on_requirement_done)** — `{"id":"c1ec26b7-526a-414b-b245-d3e3b34fde0d","dependency":"a1baaa37-ab88-44f1-93b8-31b84b7f7cbb"}`
- ✓ **complete parent A (final-reply done)**
- ✓ **poll autonomous dispatch on B** — `{"message_id":"5c6212d8-e73d-48fd-b911-748f2d5f6fc7","sender_type":"agent","sender_id":"861ba0d8-922e-4fbe-9d45-1a4c6e835967","recipient_id":"a5aaf5c9-d36e-4679-8cb8-4fdf00cdd7ec","status":"queued","title":"[自主合作] [autonomous-collab] 父需求 1778177074953 → [autonomous-collab] 子需求 1778177075020"}`
- ✓ **assert sender_id=NPC1 (row_id or config_id)** — `{"got":"861ba0d8-922e-4fbe-9d45-1a4c6e835967"}`
- ✓ **assert recipient is downstream workstation**
- ✓ **assert same-workstation skip review** — `{"status":"queued"}`

## 摘要

```json
{
  "cross_workstation": false,
  "auto_dispatch_message_id": "5c6212d8-e73d-48fd-b911-748f2d5f6fc7",
  "downstream_status": "queued"
}
```