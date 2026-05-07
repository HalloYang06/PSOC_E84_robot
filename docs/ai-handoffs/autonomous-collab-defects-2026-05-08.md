# 自主合作 UI 验收 · 缺陷清单（2026-05-08）

> 验收脚本：`scripts/validate-autonomous-collab-ui.mjs`
> 截图：`artifacts/autonomous-collab-ui/`、镜像 `docs/screenshots/v1/autonomous-collab-ui-2026-05-07.md`
> 数据：commit `3b65db5a` 上线后真跑出来的数据
> 用户原话（2026-05-08）："以用户视角全方位截图验收，并指明缺陷"

---

## 总览

UI 验收 7 项，**5 PASS / 2 FAIL**。FAIL 项里揭示了一条 **P0 路由不一致**，剩下都已记录为 P1/P2。下面 9 条按严重程度排序。

| # | 严重 | 缺陷 |
|---|---|---|
| D1 | **P0** | 自主合作派单的 recipient_type 用 `workstation`，NPC 瓷砖过滤用 `thread_workstation`，瓷砖永远拿不到自主合作消息 |
| D2 | P0 | 触发式派单表单只挂在 `/projects/[id]/2d-upgrade`，工作台和驾驶舱都没入口，新用户根本找不到 |
| D3 | P1 | CollaborationMessage 没有 metadata 列；跨工位/审核/上下游信息只能塞 body 文本，前端没解析成 chip |
| D4 | P1 | `trigger_kind` 只支持 `manual` / `on_requirement_done`；用户原话还有 `on_task_status:done` / `on_message_status:completed`，未实现 |
| D5 | P1 | `review_policy` 项目级 default / 工位级 profile 无 UI 入口，只能 SQL 直改；NPC 级也只有展示 chip 没有切换控件 |
| D6 | P1 | approve / reject 端点没加 row lock；并发审批可能 double-flip |
| D7 | P2 | NpcTile 待审区只显示 sender/title，没有"为什么需要审"提示（跨工位、policy 来源） |
| D8 | P2 | 自主合作消息派出后 watcher 是否真能拉到 queued 后的消息并真回，**本轮没真跑**（commit 3b65db5a 后只跑了协议层） |
| D9 | P2 | sender_id 用的是 row_id，前端 NpcTile 着色 `seat.id` 对比时如果是 config_id 就不一致；validate 脚本已用 set 兜过 |

---

## D1（P0） NPC 瓷砖永远拉不到自主合作消息（recipient_type 不一致）

**复现**：
1. 跑 `scripts/validate-autonomous-collab-ui.mjs`，#04 FAIL
2. 进 `/projects/proj_ai_collab/workbench`，开两个不同工位的 NPC 瓷砖
3. 用 API 触发跨工位场景（脚本内 `buildScenario('cross')`）
4. 看下游 NPC 瓷砖：**没有 📌 待审区**

**真因**：

- 触发函数 `apps/api/app/modules/requirements/service.py:532` 写死 `recipient_type="workstation"`
- NpcTile 收件箱过滤 `apps/web/app/projects/[id]/workbench/_components/npc-tile.tsx:311` 用 `recipient_type=thread_workstation`
- 两边字符串不等 → 瓷砖永远拿不到 `pending_review` 消息

**证据**：

```python
# DB 实查
SELECT recipient_type, recipient_id, status FROM collaboration_messages
WHERE message_type='requirement_dispatch' AND status='pending_review';
# recipient_type='workstation', recipient_id='执行工位'(config_id)
# 但 NPC seat 收件箱用 recipient_type='thread_workstation', recipient_id=seat.row_id
```

**修法（推荐）**：触发函数改为写 `recipient_type="thread_workstation"` + `recipient_id=downstream.id`（seat row_id），让瓷砖路由能命中。同时驾驶舱按 status 过滤的现状不受影响。

---

## D2（P0） 触发式派单表单的入口在 `/2d-upgrade`，工作台/驾驶舱都没有

**复现**：
1. 进 `/projects/proj_ai_collab/cockpit` → 驾驶舱无"创建触发式需求"按钮
2. 进 `/projects/proj_ai_collab/workbench` → 工作台也没有
3. 必须进 `/projects/proj_ai_collab/2d-upgrade` 才能用 `RequirementDispatcher`

**真因**：组件 `requirement-dispatcher.tsx` 只在 `project-2d-upgrade-game.tsx:3191` 挂载。其他两个主入口路由没有引入。

**修法**：
- 工作台顶部新加一个"触发式派单"折叠区（推荐，因为"项目→工位→NPC→线程"主战场就是工作台）
- 或在驾驶舱"待审"section 上方加一个紧凑版表单

---

## D3（P1） CollaborationMessage 没 metadata 列，跨工位/审核信息只能塞 body 文本

**复现**：
1. 看任一 pending_review 消息的 body：
   ```
   路由：项目 proj_ai_collab → 工位 ... → NPC X
   上游 NPC: Y
   跨工位：是；审核：要（来源：project_default）
   ```
2. 前端没解析这段文本，没有"跨工位""policy 来源"的 chip 显示

**真因**：模型 `CollaborationMessage` 没 metadata JSON 列；当时为了避开 schema error 改塞 body 文本。

**修法**：
- 短期：前端在 NpcTile 待审区从 body 里 regex 提取并展示 chip
- 长期：给 `collaboration_messages` 加 metadata JSON 列（带 alembic + seed.ensure_schema_extensions 双补丁，因为本仓库主用 SQLite）

---

## D4（P1） trigger_kind 只支持 manual / on_requirement_done，用户原话另两种没做

**复现**：在 RequirementDispatcher 的 trigger 下拉只有"立即派单 manual / 父需求完成 on_requirement_done"两种。

**真因**：
- `apps/api/app/modules/requirements/schemas.py` 的 `RequirementCreate.trigger_kind` Pydantic pattern 写死 `^(manual|on_requirement_done)$`
- service.py 的 `_trigger_dependent_requirements` 也只扫这一种

**修法（按用户原话扩展）**：
- 加 `on_task_status:done`：监听 `apps/api/app/modules/tasks/service.py` 状态变化
- 加 `on_message_status:completed`：监听 `collaboration_messages.status` 变更钩子
- schemas pattern 同步加；前端下拉三选一

---

## D5（P1） review_policy 三级开关只有 NPC 级有 chip，项目级 / 工位级没 UI

**复现**：
1. NPC 头部：有 `force / skip / inherit` 三态 chip（`reviewBadge`）
2. 工位分组卡：没有 "本工位 review_policy" 切换按钮
3. 项目设置页：没有 "项目默认 review_policy" 字段

**真因**：合并时只做了 NPC 层 UI；工位层 `workstation_profiles[node_id].review_policy` 和项目层 `review_policy.default` 还在 collaboration_config JSON 里，靠 SQL 手改。

**修法**：
- 项目设置 modal 加一个 `<select>`（always / cross_workstation_only / never）
- 工位分组 header 加同样的下拉
- 都走 `update_project_collaboration_config` 落库

---

## D6（P1） approve / reject 端点没加状态机锁，并发审批会 double-flip

**复现**：
1. 两个浏览器窗口同时打开 NPC 瓷砖，都看到同一条 pending_review
2. 几乎同时点"通过"
3. 当前实现：第二次 approve 会因为 status 已经是 `queued` 抛 `MESSAGE_NOT_PENDING_REVIEW` 409，但 requirement 状态可能已被改两次（race window 极小但存在）

**真因**：`apps/api/app/modules/collaboration/router.py:api_review_approve_message` 用 if 检查 status，没用 SELECT FOR UPDATE / row lock。

**修法**：
- 短期：approve 内套 `db.execute(text("SELECT ... FOR UPDATE"))`（pg）/ `BEGIN IMMEDIATE`（sqlite）
- 长期：审批端点统一走 audit trail 表，幂等 key = message_id+action

---

## D7（P2） NpcTile 待审区不显示"为什么要审"

**复现**：跨工位场景的 NpcTile 待审区只展示：
```
[发件人 NPC name]
[消息标题]
[通过] [打回]
```

没有"跨工位 → 强审"或者 "policy 来源：project_default" 的提示。

**修法**：从 body 文本 regex 拉出"跨工位：是 / 来源：xxx"渲染成 chip。也可以等 D3 加完 metadata 列后直接读字段。

---

## D8（P2） watcher 没真跑通审批通过后的下游消息

**复现**：
1. 跑 `scripts/validate-npc-autonomous-collab.mjs FORCE_MODE=cross`：协议层 PASS（消息 queued）
2. 但 watcher（thread runner）没跑起来真去 dispatch CLI
3. 没有"agent_result 真出现"的断言

**真因**：本轮把 seat.computer_node_id 错配修了（runner_pc1 → runner-pc1），但脚本没跑端到端 watcher 链；接手包 R3 才到那一步。

**修法**：写一个 `validate-autonomous-collab-watcher.mjs`，造完跨工位待审 → approve → 起 watcher → 断言 30 分钟内出现 agent_result（参考 `validate-end-to-end-reply.mjs` 的 watcher 模式）。

---

## D9（P2） sender_id 用 row_id 时 NpcTile 着色路径与 config_id 不一致

**复现**：`scripts/validate-npc-autonomous-collab.mjs` 第 268 行已经在用 `acceptedUpstreamIds = new Set([seatId, configId, rowId])` 兜底，因为消息的 sender_id 可能是 row_id（hex UUID）也可能是 config_id（中文名）。

**真因**：`_resolve_seat()` 默认返回 row_id，而前端 `seat.id` 在 collaboration_config JSON 里是 config_id。两者不统一。

**修法**：
- 派单写表前 normalize：永远写 row_id；前端 `seat.id` 显式映射成 row_id
- 或者倒过来全用 config_id；二选一，但要全链路统一

---

## 还没真跑过的链路（接手者注意）

- 跨工位 approve 后：watcher → CLI → agent_result 真回（D8）
- 同工位 immediate queued 后：watcher 同样的端到端
- 多人同时审批的并发（D6 race）

---

## 触达点速查

| 缺陷 | 文件 / 行 |
|---|---|
| D1 | `apps/api/app/modules/requirements/service.py:532` ↔ `apps/web/app/projects/[id]/workbench/_components/npc-tile.tsx:311` |
| D2 | `apps/web/app/projects/[id]/2d-upgrade/project-2d-upgrade-game.tsx:3191` |
| D3 | `apps/api/app/db/models/collaboration_message.py`（无 metadata 列） |
| D4 | `apps/api/app/modules/requirements/schemas.py`（`trigger_kind` pattern） |
| D5 | `apps/web/app/projects/[id]/workbench/_components/npc-tile.tsx:reviewBadge` 是唯一开关 UI |
| D6 | `apps/api/app/modules/collaboration/router.py:api_review_approve_message` |
| D7 | `apps/web/app/projects/[id]/workbench/_components/npc-tile.tsx:667+`（待审区） |
| D8 | 缺 `scripts/validate-autonomous-collab-watcher.mjs` |
| D9 | `apps/api/app/modules/requirements/service.py:_resolve_seat` |
