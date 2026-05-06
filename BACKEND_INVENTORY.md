# 后端能力盘点（2026-05-06）

> 用途：在动手开发任何后端功能前，先看这份地图。每个模块的状态、依赖、需要补/优化/裁剪/联通的事项都在这里。
> 更新规则：每完成一项改造就更新对应模块的"状态"和"建议"。

## 模块全景（20 个模块）

### 第一梯队：核心业务（已经完整或近完整）

#### 1. `auth` — 用户、邀请、成员、登录
- **完成度**：✅ 完整
- **关键能力**：register / login / session / me / workspace / invitation CRUD / project_members
- **已知问题**：legacy login 不校验密码（已记 memory），SuperTokens 双轨未收口（S1-1）
- **依赖**：audit（写日志）、projects（成员归属）
- **建议**：
  - 🔧 优化：S1-1 收口 legacy/SuperTokens 双轨
  - 🔧 优化：补 `password_hash` 字段（依赖 S1-3 Alembic）

#### 2. `projects` — 项目、协作配置（工位/AI provider/电脑节点）
- **完成度**：✅ 完整
- **关键能力**：项目 CRUD、collaboration_config 标准化、GitHub 同步登记、回退登记、presence 上报
- **已知**：collaboration_config 是个超级 JSON 字段，包含 `thread_workstations` / `ai_providers` / `computer_nodes` / `skill_library` / `development_workshop_stations`
- **依赖**：auth、collaboration、messages
- **建议**：
  - 🔧 优化：把 collaboration_config 里的 `skill_library` 和 `development_workshop_stations` 抽成独立表（详见下面 #15 #16）

#### 3. `tasks` — 任务生命周期、状态机、派单
- **完成度**：✅ 完整
- **关键能力**：CRUD / dispatch / plan / run / review；状态机有 H3/H4 高风险闸门强制审批
- **依赖**：projects、agents、approvals、handoffs、collaboration
- **建议**：
  - 🔧 优化：S1-4 把 dispatch 与 runners 真正打通（目前主要是登记）
  - 🔗 联通：与 claude_bridge 联通——派 NPC 任务时自动用 NPC 知识库+Skill+工坊知识打包 prompt（核心需求）

#### 4. `requirements` — 需求拆解、自动推进
- **完成度**：✅ 完整
- **关键能力**：CRUD、dispatch、accept、similar、autonomy-sweep（自动产生最终回复 + 创建后续需求）
- **依赖**：tasks
- **建议**：
  - 🔧 优化：similar 接口已有但前端没接入入口（避免重复需求）
  - 🔗 联通：与 claude_bridge 的 prompt 联通，让 Claude 知道为什么做这个任务（"上游需求"）

#### 5. `approvals` — 高风险动作审批
- **完成度**：✅ 完整
- **关键能力**：列表 / 创建 / approve / reject；H1-H4 等级
- **依赖**：tasks、audit
- **建议**：
  - 🔧 优化：补 `/approvals/pending-mine` 端点（当前用户待审），驾驶舱里可以高亮显示
  - 🔧 优化：审批通过后自动联动任务状态（目前需要外层手动）

#### 6. `handoffs` — 任务/上下文交接
- **完成度**：✅ 完整
- **关键能力**：列表、为任务创建 handoff、accept handoff
- **依赖**：tasks、agents
- **建议**：
  - 🔗 联通：**与 claude_bridge 联通**——切换 NPC 线程时自动生成 handoff 包（NPC 核心价值的实现点）
  - 🔧 优化：handoff payload 字段标准化，与 NPC 知识库对接（让接手 AI 读到完整上下文）

#### 7. `agents` — Agent 注册表
- **完成度**：✅ 完整
- **关键能力**：列出 / 创建 / 启用
- **依赖**：tasks、collaboration
- **建议**：
  - 🔗 联通：agents 表很可能与"NPC"重叠，需要明确 agent vs npc seat（workstation）的区分（agent 是定义，workstation 是项目级实例）
  - ✂️ 裁剪：很可能不需要新建"NPC 表"，复用 ProjectThreadWorkstation + Agent 即可

---

### 第二梯队：执行/集成层

#### 8. `runners` — 真实执行节点
- **完成度**：⚠️ 部分（核心 API 全，但调度闭环未真正跑通）
- **关键能力**：register / heartbeat / next-task / inbox / ack / complete / logs / result / transition
- **依赖**：tasks、collaboration
- **建议**：
  - 🔧 优化：S1-4 调度闭环；让任务真正被 runner 领取并回写
  - 🔗 联通：runner 的 inbox 与 collaboration messages 已经映射，但 UI 层显示分散，要联通

#### 9. `git` — Git 同步、回退
- **完成度**：⚠️ 部分（端点有，真正执行靠 runner）
- **关键能力**：status / workspace / sync-github / rollback；返回 `recommended_workstations`（智能推荐）
- **依赖**：projects、runners、approvals
- **建议**：
  - 🔧 优化：S1-5 真正执行闭环（Clone/Branch/PR/Merge）
  - 🎯 杀手锏：`workspace.recommended_workstations` 后端有但前端没用上！这是"智能推荐工位/NPC"的现成能力
  - 🔧 优化：rollback 必须强制走 approvals（高风险）

#### 10. `collaboration` — 协作消息池、工位 CRUD、电脑节点
- **完成度**：✅ 完整
- **关键能力**：summary / messages（消息池）/ projects/{id}/computer-nodes（电脑节点 CRUD）/ runner-relay
- **依赖**：projects、messages、runners、agents
- **建议**：
  - ⚠️ **与 messages 模块有重叠** —— 需要厘清：collaboration_messages 表 vs messages 表，按理应合并或明确分工
  - 🔗 联通：runner relay → 把派给 NPC 的指令转成 runner 命令，已经有，前端要可视化"指令在路上"

#### 11. `messages` — 实体消息（实体级评论流）
- **完成度**：✅ 完整
- **关键能力**：create_entity_message / list_entity_messages —— 给 task/approval/handoff 等实体加评论
- **依赖**：projects
- **建议**：
  - ⚠️ 与 collaboration 模块功能重叠 —— **需要裁剪决策**：保留哪个？
  - 推荐：`collaboration_messages` 是核心通讯（含 dispatch/relay），`messages` 是实体评论流，可以并存但要明确边界

---

### 第三梯队：知识/记忆/记录类

#### 12. `context` — 上下文健康度
- **完成度**：⚠️ 骨架（有 model `context_health_records`，业务逻辑只在 router 拍快照，没"健康评分"）
- **关键能力**：当前主要是写入快照
- **依赖**：tasks、agents
- **建议**：
  - 🔧 优化：S2-6 上下文健康度机制——补 Green/Yellow/Orange/Red 评分逻辑
  - 🔗 联通：**与 NPC 切换线程联通**——切线程前先看上下文健康度，Orange/Red 强制生成 handoff

#### 13. `knowledge` — 项目级/通用知识库
- **完成度**：⚠️ 部分（有 router 但功能模糊，到底是什么知识？）
- **关键能力**：list knowledge entries
- **建议**：
  - ⚠️ **必须厘清边界**：knowledge 是什么？vs NPC 个人知识库 vs 工坊共享知识 vs 需求 context_summary
  - 推荐定位：**项目级公共知识库**（与具体 NPC 无关的通用文档），与 development（工坊知识）和 NPC metadata.npc_knowledge 形成三层
  - 🔧 优化：补 CRUD（创建/编辑/分类）

#### 14. `development` — 开发工坊
- **完成度**：⚠️ 部分（前端逻辑完整，后端只有 init code）
- **关键能力**：工坊定义在前端 `lib/development-workshop.ts` 硬编码 + Project.collaboration_config 的 development_workshop_stations
- **依赖**：projects
- **建议**：
  - 🔧 **大补**：根据用户最新定义"工坊 = 几个 NPC 共享的知识库"，需要：
    - 抽出独立 `development_workshops` 表（id / project_id / name / 共享知识 markdown 路径 / tags）
    - `workshop_npc` 关联表（多对多：NPC ↔ 工坊）
    - 新增端点：`GET /workshops/{id}` `POST /workshops/{id}/npcs/{npc_id}` 挂载 NPC
  - 🔗 联通：派任务时如果选了 NPC，自动把它所在所有工坊的知识汇总进 prompt

#### 15. **Skill 仓库** — 当前不是独立模块（需要补）
- **完成度**：❌ 未独立成模块
- **现状**：
  - 前端硬编码 `apps/web/lib/platform-skills.ts` 默认 skill 库
  - 项目自定义 skill 存 `Project.collaboration_config.skill_library` JSON
  - NPC 装配 skill 存 `metadata.skill_loadout` 数组
  - actions.ts 有 `创建项目Skill` `导入Github项目Skill` `导入AgencyAgents项目Skill包` 等 server action
- **建议**：
  - 🆕 **新建 `apps/api/app/modules/skills` 模块**：
    - 独立 `skills` 表（id / project_id / name / description / category / source / created_by / metadata）
    - 端点：`GET /skills` `POST /skills` `PATCH /skills/{id}` `DELETE /skills/{id}` `POST /skills/import-github`
    - 把现有 server actions 的逻辑迁移过来（或保留前端 action 但底层走新表）
  - 🔗 联通：NPC、工坊都从 skills 表索引装备
  - 🎯 NPC 卡 / 工坊卡显示装备的 skill 时直接 join 这个表

#### 16. `lab` — 硬件实验、检查清单、硬件审批
- **完成度**：✅ 完整
- **关键能力**：status / checklist / audit / approvals/hardware / check-records / short-chain
- **依赖**：runners、approvals、tasks、audit
- **建议**：
  - 🔧 优化：补"硬件资产"概念（板卡 ID / 固件版本绑定）
  - 🔗 联通：与 development 工坊联通——硬件工坊的 NPC 操作硬件时走 lab 审批流

---

### 第四梯队：横切关注

#### 17. `audit` — 审计日志
- **完成度**：✅ 完整
- **关键能力**：分页查询 + 各模块统一调用 `create_audit_log`
- **建议**：
  - 🔧 优化：增加归档/分区策略（数据量大）

#### 18. `usage` — token 用量
- **完成度**：⚠️ 骨架（端点有，自动采集没接入）
- **建议**：
  - 🔗 **联通 claude_bridge**：每次 prompt 生成时记录 token 估算
  - 🔗 联通 runner：runner 上报 AI 调用时自动记 usage

#### 19. `claude_bridge` — Claude Code 桥接（本轮新加）
- **完成度**：✅ 已实现 3 端点（project context / task prompt / handoff）
- **建议**：
  - 🆕 补 `GET /npc/{npc_id}/context`——按 NPC 维度返回（核心：减少 AI 换手成本）
  - 🆕 补 `GET /workshops/{ws_id}/context`——按工坊维度
  - 🔗 联通 development（工坊知识）、handoffs（交接历史）、context（健康度）

#### 20. `read_access.py` — 工具：项目级读权限校验
- **完成度**：✅ 完整
- **建议**：
  - 🔧 优化：与 `app/common/access.py`（写权限）合并，统一权限策略中心

---

## 关系图（核心实体）

```
                      ┌─────────────┐
                      │   Project   │ ← 一切的容器
                      └──────┬──────┘
                             │
    ┌──────────┬─────────────┼─────────────┬──────────────┐
    │          │             │             │              │
    ▼          ▼             ▼             ▼              ▼
┌────────┐ ┌────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐
│Members │ │  Task  │  │Workshop  │  │   NPC    │  │ Runner    │
│        │ │   ←──┼──┤(开发工坊)│  │(workstn) │  │(电脑节点) │
└────────┘ └────┬───┘  └────┬─────┘  └────┬─────┘  └─────┬─────┘
                │           │             │              │
                │           │ 共享知识     │个人知识      │执行环境
                │           ▼             ▼              │
                │      ┌─────────┐   ┌─────────┐         │
                │      │ Skill   │←──┤ Skill   │         │
                │      │（共用） │   │ loadout │         │
                │      └─────────┘   └─────────┘         │
                │                                        │
                ├──── handoff ───── handoffs ────────────┤
                ├──── approval ──── approvals ───────────┤
                ├──── requirement ─ requirements ────────┤
                ├──── audit_log ─── audit ───────────────┤
                ├──── usage_log ─── usage ───────────────┤
                ▼                                        ▼
        ┌──────────────────────────────────────────────────┐
        │     CollaborationMessage / Message               │
        │     (跨 NPC、跨任务的消息流 + 实体评论)          │
        └──────────────────────────────────────────────────┘

工作流：
  人类 → 创建 Requirement → 拆 Task → 选 NPC → NPC 在它当前线程执行
                                       │
                                       ├ 自动注入：NPC 知识库 + Skill + 工坊共享知识 + 上游需求
                                       │
                                       ▼
                                    Runner 在电脑上跑
                                       │
                                       ├ 高风险动作 → 触发 Approval（人工审批）
                                       │
                                       ▼
                                    回执 → 最终回复 → Handoff
```

---

## 总动作清单（按优先级，先关系，后开发）

### P0：先把"NPC 减少 AI 换手成本"这条核心链路打通
1. **新增 Skill 模块**（#15）—— 独立 skills 表 + CRUD
2. **完善 Workshop 后端**（#14）—— 独立表 + NPC 多对多关联
3. **NPC 上下文打包端点**（#19 补）—— `GET /claude-bridge/npc/{id}/context` 自动汇总：NPC 个人知识 + 工坊知识 + Skill + 当前任务 + 最近交接
4. **handoff 与 NPC 知识库联通**（#6）—— 切线程时自动生成 handoff，新 AI 进来读 handoff + NPC 知识 = 0 指导接手

### P1：消除重复 + 补缺口
5. **collaboration vs messages 边界裁剪**（#10 #11）—— 决定谁主谁辅
6. **knowledge 模块定位明确**（#13）—— 项目级公共知识库，CRUD 补全
7. **context 健康度业务逻辑**（#12）—— 评分 + 强制交接

### P2：联通已有但未用上的能力
8. **git workspace.recommended_workstations 接到前端**（#9）—— 智能推荐工位
9. **requirements similar 搜索接到前端**（#4）—— 防止重复需求
10. **usage 自动采集**（#18）—— claude_bridge 每次拼 prompt 时记 token 估算

### P3：基础工程
11. S1-1 SuperTokens 收口（已有任务）
12. S1-2 权限审计（已有任务）
13. S1-3 Alembic 接入（已有任务）
14. S1-4 Runner 调度闭环（已有任务）
15. S1-5 Git 执行链（已有任务）

---

## 决策点（需要用户确认）

1. **collaboration_messages vs messages**：保留哪个？（影响很多模块）
2. **Skill 表是否独立**：当前在 JSON 里也能跑，独立表能换来什么？
3. **Workshop 表是否独立**：当前在 JSON 里也能跑
4. **knowledge 模块定位**：留作"项目级公共知识"还是裁剪掉？
