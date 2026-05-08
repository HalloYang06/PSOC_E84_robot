# NPC 自主合作验收报告

- 时间：2026-05-08T01:20:23.576Z → 2026-05-08T01:20:24.008Z
- 项目：proj_ai_collab
- 整体：✅ PASS


## 步骤

- ✓ **login**
- ✓ **fetch project** — `proj_ai_collab`
- ✓ **pick pair** — `{"upstream":"前端工位","upstream_node":"runner-pc1","downstream":"执行工位","downstream_node":"runner-nanopi","cross_workstation":true}`
- ✓ **create parent requirement A** — `{"id":"411f84fd-9270-43c2-ad62-098079722ec2"}`
- ✓ **dispatch parent A → NPC1**
- ✓ **create child requirement B (trigger=on_requirement_done)** — `{"id":"4fedd8e0-b9e9-44e7-b246-2e87d70e0bb8","dependency":"411f84fd-9270-43c2-ad62-098079722ec2"}`
- ✓ **complete parent A (final-reply done)**
- ✓ **poll autonomous dispatch on B** — `{"message_id":"24bb485f-f061-4aed-a0be-58f5d2358679","sender_type":"agent","sender_id":"861ba0d8-922e-4fbe-9d45-1a4c6e835967","recipient_id":"52e09817-08ad-431c-a0a8-86cb9a0480e9","status":"pending_review","title":"[自主合作] [autonomous-collab] 父需求 1778203223697 → [autonomous-collab] 子需求 1778203223777"}`
- ✓ **assert sender_id=NPC1 (row_id or config_id)** — `{"got":"861ba0d8-922e-4fbe-9d45-1a4c6e835967"}`
- ✓ **assert recipient is downstream workstation**
- ✓ **assert cross-workstation requires review** — `{"status":"blocked"}`
- ✓ **assert approve flips message to queued**
- ✓ **assert approve flips requirement to queued**
- ✓ **assert watcher ack flips message to acked**

## 摘要

```json
{
  "cross_workstation": true,
  "auto_dispatch_message_id": "24bb485f-f061-4aed-a0be-58f5d2358679",
  "downstream_status": "blocked"
}
```