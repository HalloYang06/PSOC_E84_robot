# NPC 自主合作验收报告

- 时间：2026-05-07T17:21:01.523Z → 2026-05-07T17:21:01.850Z
- 项目：proj_ai_collab
- 整体：✅ PASS


## 步骤

- ✓ **login**
- ✓ **fetch project** — `proj_ai_collab`
- ✓ **pick pair** — `{"upstream":"前端工位","upstream_node":"runner-pc1","downstream":"执行工位","downstream_node":"runner-nanopi","cross_workstation":true}`
- ✓ **create parent requirement A** — `{"id":"42346aed-6d51-44d2-b592-ea8572b348ae"}`
- ✓ **dispatch parent A → NPC1**
- ✓ **create child requirement B (trigger=on_requirement_done)** — `{"id":"d7428e55-ebad-4362-8168-7a7fc06eaae5","dependency":"42346aed-6d51-44d2-b592-ea8572b348ae"}`
- ✓ **complete parent A (final-reply done)**
- ✓ **poll autonomous dispatch on B** — `{"message_id":"c19cec3a-8457-497b-b998-d98b76d03561","sender_type":"agent","sender_id":"861ba0d8-922e-4fbe-9d45-1a4c6e835967","recipient_id":"执行工位","status":"pending_review","title":"[自主合作] [autonomous-collab] 父需求 1778174461626 → [autonomous-collab] 子需求 1778174461700"}`
- ✓ **assert sender_id=NPC1 (row_id or config_id)** — `{"got":"861ba0d8-922e-4fbe-9d45-1a4c6e835967"}`
- ✓ **assert recipient is downstream workstation**
- ✓ **assert cross-workstation requires review** — `{"status":"blocked"}`
- ✓ **assert approve flips message to queued**
- ✓ **assert approve flips requirement to queued**

## 摘要

```json
{
  "cross_workstation": true,
  "auto_dispatch_message_id": "c19cec3a-8457-497b-b998-d98b76d03561",
  "downstream_status": "blocked"
}
```