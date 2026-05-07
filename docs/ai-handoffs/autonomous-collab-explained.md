# NPC 自主合作 + 工位自主交流 · 说明文档

> 上线于 commit `3b65db5a`，2026-05-08 起 D1/D2/D6/D7 修复同步合入。
> 用户原话（2026-05-08）："然后 NPC 之间的合作，还有工位之间的自主交流，记住这两项啊，别觉得难就不干，然后这两项都要加人工审批，也可以免审。"

---

## 一句话定义

**自主合作** = 上游 NPC 完成它那条需求后，平台自动以"上游 NPC 的身份"给下游 NPC 派一条新需求，跨工位时强制走人审，同工位免审。

它解决的是"NPC 之间的合作"和"工位之间的自主交流"——之前都得人手动派单。现在父需求 done 自动触发，只在跨工位时停下来等用户点"通过/打回"。

---

## 核心结构（项目 → 工位 → NPC → 线程）

```
项目 (project)
└── 工位 (computer_node = 一台电脑)
    └── NPC (seat = 一个长期职责，绑一个 provider)
        └── 线程 (thread = 一次 CLI 任务进程)
```

自主合作发生在 **NPC 层**：父需求挂在上游 NPC（target_seat_id=NPC1），完成时触发函数扫描下游需求（dependency_requirement_id=父.id + trigger_kind=on_requirement_done），自动以上游 NPC 身份给下游 NPC 派单。

跨工位 vs 同工位：判定靠 `seat.computer_node_id` 是否相等。

---

## 数据模型

### 1. requirement 三新字段（commit `3b65db5a`）

文件：`apps/api/app/db/models/requirement.py`

| 字段 | 类型 | 含义 |
|---|---|---|
| `target_seat_id` | str | 触发后派给哪个 NPC（seat.row_id 或 config_id） |
| `trigger_kind` | str | `manual`（默认） / `on_requirement_done` |
| `dependency_requirement_id` | str | 上游 requirement.id（仅 trigger=on_requirement_done 用） |

SQLite 通过 `seed.py:ensure_schema_extensions` 自动 ALTER TABLE 加列。

### 2. CollaborationMessage（自主合作消息）

派出去的消息字段（在 `collaboration_messages` 表里）：

| 字段 | 自主合作派单时的值 |
|---|---|
| `message_type` | `requirement_dispatch` |
| `sender_type` | `agent`（不是 human） |
| `sender_id` | 上游 NPC 的 row_id |
| `recipient_type` | `thread_workstation`（**D1 修复后**，旧实现是 `workstation`） |
| `recipient_id` | 下游 NPC 的 row_id（**D1 修复后**，旧实现是 config_id） |
| `agent_id` | 下游 NPC 的 config_id（保留给 watcher 路由） |
| `status` | `queued`（同工位免审） / `pending_review`（跨工位要审） |
| `body` | 含路由摘要文本：`跨工位：是/否；审核：要/免（来源：xxx）` |
| `dedupe_key` | `auto_collab_dispatch:{父req.id}:{子req.id}` 防重复触发 |

> ⚠️ **CollaborationMessage 没 metadata 列**。跨工位/审核/上下游信息只能塞 body 文本（详见 D3 缺陷）。

---

## 触发链时序

```
用户/上游 NPC 把父需求改成 done
        ↓
update_requirement / add_requirement_final_reply / run_requirement_action
        ↓
service._trigger_dependent_requirements(parent)
        ↓ 扫描所有满足条件的下游：
        ↓   dependency_requirement_id == parent.id
        ↓   trigger_kind == "on_requirement_done"
        ↓   status in {waiting_response, queued, blocked}
        ↓
对每个下游：_resolve_review_for_dispatch(下游, 上游, 项目)
        ↓
  跨工位 + 没被 skip → requires_review=True
        ↓                         ↓
  same workstation             cross
  status=queued                 status=pending_review + req.status=blocked
        ↓                         ↓
  立即可被 watcher 拉走         在 NPC 瓷砖待审区等用户点 [通过]
                                  ↓
                                 approve → message=queued + req=queued
                                 reject  → message=cancelled + req=cancelled
```

代码触达点：

| 步骤 | 文件 | 函数 |
|---|---|---|
| 触发扫描 | `apps/api/app/modules/requirements/service.py` | `_trigger_dependent_requirements` |
| review 决策 | 同上 | `_resolve_review_for_dispatch` |
| 落消息 | 同上 | `repo.create_requirement_collaboration_message` |
| 审批通过 | `apps/api/app/modules/collaboration/router.py:1382` | `api_review_approve_message` |
| 审批打回 | 同上 `:1416` | `api_review_reject_message` |

---

## 三级 review_policy 决策树

判定优先级：**NPC > 工位 > 项目 default > 内置默认（cross_workstation_only）**

```
1. 看下游 NPC seat.extra_data.review_policy：
   - "force"   → 强制审，require=True，source=npc:force
   - "skip"    → 强制免，require=False，source=npc:skip
   - "inherit" → 跳到第 2 步

2. 看下游工位 project.collaboration_config.workstation_profiles[node_id].review_policy：
   - "force"   → require=True，source=workstation:force
   - "skip"    → require=False，source=workstation:skip
   - "inherit" → 跳到第 3 步

3. 看项目 default project.collaboration_config.review_policy.default：
   - "always"                  → require=True，source=project_default:always
   - "never"                   → require=False，source=project_default:never
   - "cross_workstation_only" → 跳到第 4 步（默认值）

4. 内置：
   - 跨工位 → require=True，source=builtin:cross_only
   - 同工位 → require=False，source=builtin:cross_only
```

实现：`_resolve_review_for_dispatch` in `service.py`。返回 dict `{requires_review: bool, source: str}`。

---

## 与老 `follow_up_from_requirement_id` 链的区别

代码里有 `_maybe_create_follow_up_requirement` / `follow_up_from_requirement_id`（在 `requirements/service.py`）。**这不是自主合作**——是任务执行的**复查链**：一条需求执行不到位时，watcher 自动开一条 follow-up 续做。

| 维度 | follow_up（老） | autonomous_collab（新） |
|---|---|---|
| 触发方 | watcher（系统） | 用户改父需求 done |
| 上游 NPC | 同一个 NPC | 可指定不同 NPC |
| 跨工位 | 不考虑 | 强制走审 |
| 字段 | `follow_up_from_requirement_id` | `dependency_requirement_id` + `trigger_kind` |
| 用途 | 续做 / 复检 | 多 NPC / 多工位的合作流 |

两套字段独立存在，互不干扰。

---

## 已知限制（详见 defects 文档）

参照 `docs/ai-handoffs/autonomous-collab-defects-2026-05-08.md`：

| 缺陷 | 状态 |
|---|---|
| D1 NpcTile 路由不一致 | ✅ 已修（recipient_type=thread_workstation） |
| D2 触发表单只在 /2d-upgrade | ✅ 已修（工作台也加了） |
| D6 approve 并发锁 | ✅ 已修（带 WHERE 守护的 UPDATE） |
| D7 待审区"为什么要审" | ✅ 已修（跨工位/policy 来源 chip） |
| D3 CollaborationMessage 没 metadata 列 | ⏳ 短期 regex from body |
| D4 trigger_kind 只支持 2 种 | ⏳ on_task_status / on_message_status 待加 |
| D5 review_policy 项目级/工位级 UI 缺 | ⏳ 暂只能 SQL 改 |
| D8 watcher 端到端没真跑 | ⏳ 协议 PASS，watcher 链待写脚本 |
| D9 sender_id row_id vs config_id | ⏳ 验证脚本 set 兜底 |

---

## 端到端验证脚本

| 脚本 | 类型 | 跑法 |
|---|---|---|
| `scripts/validate-npc-autonomous-collab.mjs` | 协议层（API） | `FORCE_MODE=cross` / `FORCE_MODE=same` |
| `scripts/validate-autonomous-collab-ui.mjs` | UI（Playwright） | 默认 `WEB_BASE=http://127.0.0.1:3100` |

输出：
- 截图：`artifacts/autonomous-collab-ui/`
- 报告：`docs/screenshots/v1/`
