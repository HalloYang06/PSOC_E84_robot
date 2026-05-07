# NPC 自主合作 + 工位自主交流 · 使用文档（0 → 1）

> 给运营/PM/普通用户用。开发文档见 `autonomous-collab-explained.md`。
> 验收截图：`artifacts/autonomous-collab-ui/`、`docs/screenshots/v1/autonomous-collab-ui-2026-05-07.md`。

---

## 你能做什么

- 让 **NPC A 完成它的需求** 时，自动派一条新需求给 **NPC B**（不用你手动派）
- 跨工位（NPC A 和 B 在两台不同电脑）时，停下来等你点"通过"才会真派
- 同工位（同电脑）时，立刻派给 B
- 全部都在 **NPC 工作台** 里就地处理，不用切页

---

## 0 → 1 流程

### Step 1 · 进项目工作台

1. 登录 → `/projects` 选你的项目
2. 进 `/projects/{id}/cockpit` 看驾驶舱
3. 点驾驶舱顶部 "**打开工作台 →**" 进 `/projects/{id}/workbench`

工作台左栏会按"工位"分组列出所有 NPC。

### Step 2 · 打开两个 NPC 瓷砖

- 点左栏 NPC 行右侧 **+** 号 → 该 NPC 的瓷砖打开在右侧主区
- 想多开就再点别的 + 号；4 个以内自动 2×2 排，更多自动滚

> 提示：截图见 `03-workbench-after.png`。

### Step 3 · 打开"📌 触发式派单"表单

工作台主区顶部有一个折叠按钮：

```
[ ＋ 触发式派单（指定 NPC + 触发条件）]
```

点开后：

| 字段 | 怎么填 |
|---|---|
| 标题 | 一句话说要做什么 |
| 目标 NPC | 下拉选下游 NPC |
| 触发条件 | `manual`：立即派 / `after_requirement`：等前置完成再派 |
| 前置需求 | 仅 `after_requirement` 出现，下拉选父需求 |
| 内容 | 任务说明 + 验收标准 |

点 [立即派发] 或 [创建（等待前置完成）]。

> 修复前这个表单只在 `/projects/{id}/2d-upgrade` 那条线，普通用户找不到（D2）。现在工作台和 2D 模式两条线都有。

### Step 4a · 同工位场景（免审）

如果父需求 NPC 和子需求 NPC 在**同一台电脑**（computer_node_id 相同）：

1. 父需求被你标 done（在 NPC 瓷砖里写完最终回执 → 标 done）
2. 平台立刻给下游 NPC 瓷砖派一条新消息，状态 = `queued`
3. 下游 NPC 的 watcher 拉到，自动开始干

下游瓷砖里能看到一条 `[自主合作] 父→子` 标题的消息。

### Step 4b · 跨工位场景（要审）

如果父子需求 NPC 在**不同电脑**：

1. 父需求标 done
2. 下游 NPC 瓷砖顶部出现 **"📌 待审：自主合作消息"** 黄色区
3. 这条消息上还会显示：`跨工位` chip + `policy: builtin:cross_only`（或其他来源） chip + 上游 NPC 名
4. 你点 **[通过]** → 消息状态变 `queued`，下游 NPC 才开始干
5. 你点 **[打回]** → 消息状态变 `cancelled`，下游需求也变 `cancelled`

你也可以在驾驶舱（cockpit）顶部的"📌 待审：NPC 自主合作消息"区集中审一批。

> 截图：`04-cross-pending-review-after.png`、`05-cross-approve-after.png`、`07-cockpit-pending-after.png`。

---

## 改 review_policy（控制审 vs 免审）

三级开关，优先级 **NPC > 工位 > 项目 default**：

### 项目级 default（暂只能 SQL）

```sql
-- 在 projects.collaboration_config JSON 里
UPDATE projects
SET collaboration_config = json_set(
  COALESCE(collaboration_config, '{}'),
  '$.review_policy.default',
  'always'        -- 或 'never' / 'cross_workstation_only'（默认）
)
WHERE id = 'proj_ai_collab';
```

或用 API：`PATCH /api/projects/{id}/collaboration-config` body `{"review_policy":{"default":"always"}}`

### 工位级（暂只能 SQL/API）

```sql
UPDATE projects SET collaboration_config = json_set(
  COALESCE(collaboration_config, '{}'),
  '$.workstation_profiles."runner-pc1".review_policy',
  'force'   -- 或 'skip' / 'inherit'
) WHERE id = 'proj_ai_collab';
```

### NPC 级（**有 UI**）

打开 NPC 瓷砖头部，找小 chip：

- `审force` → 这个 NPC 收的消息一律走审（即使同工位）
- `审skip` → 这个 NPC 收的消息一律免审（即使跨工位）
- `审inherit` → 跳到工位/项目级判定

> ⏳ 项目级和工位级 UI 是缺陷 D5，暂时只能 API/SQL。

---

## 审完后：watcher 自动消化（同流）

`status=queued` 后，下游 NPC 工位的 thread watcher（参见 `start-thread-watcher.ps1`）会拉到这条 `requirement_dispatch`，调起 NPC 的 Claude/Codex 线程去处理。

如果 watcher 没跑，需要在那台电脑手动起：

```powershell
# 在下游 NPC 所在的电脑
.\start-thread-watcher.ps1 -SeatId <seat-row-id> -ProviderId <claude|codex>
```

> ⏳ 端到端"approve → watcher → AI 真回"链路本轮没真跑（缺陷 D8）。协议层（消息状态流转）已 PASS。

---

## 验收脚本（自检）

平台开发者可跑：

```bash
# 协议层（最快，纯 API）
FORCE_MODE=cross node scripts/validate-npc-autonomous-collab.mjs   # 跨工位
FORCE_MODE=same  node scripts/validate-npc-autonomous-collab.mjs   # 同工位

# UI 层（Playwright，自动开浏览器、跑流程、截图）
WEB_BASE=http://127.0.0.1:3100 node scripts/validate-autonomous-collab-ui.mjs
```

跑完看：
- `artifacts/npc-autonomous-collab/report-*.md`
- `artifacts/autonomous-collab-ui/report.md`
- `docs/screenshots/v1/autonomous-collab-ui-2026-05-07.md`

---

## 常见疑问

**Q：派出去的消息瓷砖看不到？**
A：commit `3b65db5a` 第一版有路由 bug（recipient_type 不匹配，缺陷 D1），已在 2026-05-08 修复。如果你看到老消息，可以删掉重发；新消息瓷砖能立刻收到。

**Q：怎么阻止某条触发？**
A：父需求标 done 之前，把子需求 status 改成 `cancelled`（驾驶舱"需求清单"或 API `PATCH /api/requirements/{id}`）。`_trigger_dependent_requirements` 只会扫 `waiting_response/queued/blocked` 状态。

**Q：同一对父子需求会重复触发吗？**
A：不会。dedupe_key 是 `auto_collab_dispatch:{父}:{子}`，重复触发会拿到同一条消息。

**Q：审了几条以后想"放权"，怎么办？**
A：把那个下游 NPC 的 review_policy 改成 `skip`（瓷砖头部 chip 点击切换），后面这个 NPC 收的消息全免审；或者改成 `inherit` 让工位/项目 default 接管。

**Q：链路图？**
A：见 `autonomous-collab-explained.md` 的"触发链时序"。
