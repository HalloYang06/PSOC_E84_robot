---
name: "role-claim"
description: "Claim or verify a project role before doing any work. Use when a thread joins the AI collaboration platform project, when a role may already be occupied, or when a thread needs to switch to assistant or handoff mode."
---

# Role Claim

Read these files in order before doing any implementation:

1. `README.md`
2. `AI协作平台第一版开发入口.md`
3. `AI身份认领与统一协作规则.md`
4. `AI协作平台开发AI分工文档.md`

Follow this workflow:

1. Confirm the role you intend to claim.
2. Check whether the role is already occupied.
3. If occupied, switch to one of:
   - assistant role
   - task-specific handoff role
   - wait for human reassignment
4. State your writable scope, forbidden scope, expected inputs, and expected outputs.
5. Do not modify code until the role is confirmed.

Use this output format:

```text
【AI 身份认领】
认领身份:
当前角色状态:
所属组:
主要职责:
我可以负责的目录:
我不能擅自修改的目录:
我需要的输入:
我会输出的结果:
我需要联系的其他 AI:
我的权限边界:
我确认遵守统一协作规则: 是
```

If your role is already occupied, say so explicitly and propose either a sub-role or a task-specific handoff role.

